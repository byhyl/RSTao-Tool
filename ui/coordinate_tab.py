"""坐标转换面板 — 支持点文件/影像导入 + 7参数 + GIS 级影像查看器"""
import os
from tkinter import filedialog, messagebox

import customtkinter as ctk
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from core.coordinate_system import (CHINA_EPSG, COMMON_EPSG, CoordinateSystem,
                                     PointSet, RasterInfo, SevenParams)
from .raster_viewer import RasterViewer
from common.utils import safe_execute
from .theme import THEME, FONT_NORMAL, FONT_SMALL, FONT_SUBTITLE, SECTION_STYLE

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


class CoordinateTab(ctk.CTkFrame):
    """坐标系转换面板"""

    def __init__(self, parent, status_vars=None):
        super().__init__(parent, fg_color=THEME["bg"])
        self.cs = CoordinateSystem()
        self.point_set: PointSet = PointSet()
        self.raster_info: RasterInfo = None
        self._view_mode = "points"  # "points" or "raster"
        self._create_ui()

    def _create_ui(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # === 左侧控制面板 ===
        side = ctk.CTkFrame(self, width=310, fg_color=THEME["panel"])
        side.grid(row=0, column=0, sticky="ns", padx=(0, 8))
        side.grid_propagate(False)

        ctk.CTkLabel(side, text="坐标系转换", font=("Microsoft YaHei UI", 16, "bold")
                    ).pack(anchor="w", padx=14, pady=(12, 6))

        if not self.cs.available:
            ctk.CTkLabel(side, text="⚠ pyproj 未安装\n请执行: pip install pyproj",
                        font=FONT_SMALL, text_color=THEME["warning"]).pack(padx=14, pady=10)
            self._add_empty_right()
            return

        # === 数据源 ===
        self._section(side, "数据源")
        src_card = ctk.CTkFrame(side, **SECTION_STYLE)
        src_card.pack(fill="x", padx=10, pady=(0, 8))

        btn_row = ctk.CTkFrame(src_card, fg_color="transparent")
        btn_row.pack(fill="x", padx=10, pady=8)
        ctk.CTkButton(btn_row, text="导入点文件", command=self._load_points,
                     height=28, font=FONT_SMALL).pack(side="left", fill="x", expand=True, padx=(0, 3))
        ctk.CTkButton(btn_row, text="导入影像", command=self._load_raster,
                     height=28, font=FONT_SMALL).pack(side="right", fill="x", expand=True, padx=(3, 0))

        self.src_label = ctk.CTkLabel(src_card, text="未加载数据", font=FONT_SMALL,
                                      text_color=THEME["text_muted"])
        self.src_label.pack(padx=10, pady=(0, 8))

        # === 坐标系设置 ===
        self._section(side, "转换参数")
        param_card = ctk.CTkFrame(side, **SECTION_STYLE)
        param_card.pack(fill="x", padx=10, pady=(0, 8))

        all_epsg = {**COMMON_EPSG, **CHINA_EPSG}
        ctk.CTkLabel(param_card, text="源坐标系", font=FONT_SMALL).pack(anchor="w", padx=10, pady=(8, 2))
        self.src_epsg = ctk.CTkComboBox(param_card, values=list(all_epsg.keys()), font=FONT_SMALL)
        self.src_epsg.pack(fill="x", padx=10)
        self.src_epsg.set("WGS84")

        ctk.CTkLabel(param_card, text="目标坐标系", font=FONT_SMALL).pack(anchor="w", padx=10, pady=(6, 2))
        self.dst_epsg = ctk.CTkComboBox(param_card, values=list(all_epsg.keys()), font=FONT_SMALL)
        self.dst_epsg.pack(fill="x", padx=10)
        self.dst_epsg.set("CGCS2000 / 3度 117E")

        # 7参数开关
        self.use7p = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(param_card, text="使用 7 参数模型", variable=self.use7p,
                        command=self._toggle_7param, font=FONT_SMALL).pack(anchor="w", padx=10, pady=(8, 2))

        self.p7_frame = ctk.CTkFrame(param_card, fg_color="transparent")
        self.p7_entries = {}
        fields = [("Dx(m)", "dx", 0), ("Dy(m)", "dy", 0), ("Dz(m)", "dz", 0),
                   ("Rx(\")", "rx", 0), ("Ry(\")", "ry", 0), ("Rz(\")", "rz", 0),
                   ("S(ppm)", "scale", 0)]
        for label, key, val in fields:
            row = ctk.CTkFrame(self.p7_frame, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=1)
            ctk.CTkLabel(row, text=label, font=("Consolas", 9), width=50,
                        text_color=THEME["text_secondary"]).pack(side="left")
            e = ctk.CTkEntry(row, font=("Consolas", 10), height=24)
            e.insert(0, str(val))
            e.pack(side="left", fill="x", expand=True)
            self.p7_entries[key] = e

        # 预设
        preset_row = ctk.CTkFrame(param_card, fg_color="transparent")
        preset_row.pack(fill="x", padx=10, pady=(4, 8))
        self.p7_preset = ctk.CTkComboBox(preset_row, values=["自定义", "WGS84_to_CGCS2000", "BJ54_to_WGS84", "XA80_to_WGS84"],
                                         font=FONT_SMALL, command=self._on_preset)
        self.p7_preset.pack(fill="x")
        self.p7_preset.set("自定义")
        self.p7_frame.pack_forget()

        # === 转换 ===
        ctk.CTkButton(side, text="执行转换", command=self._execute,
                     fg_color=THEME["accent"], hover_color=THEME["accent_hover"],
                     height=32, font=FONT_NORMAL, corner_radius=6).pack(fill="x", padx=10, pady=(6, 2))

        ctk.CTkButton(side, text="导出结果 CSV", command=self._export_csv,
                     fg_color="transparent", border_width=1, border_color=THEME["border"],
                     text_color=THEME["text_primary"], height=28, font=FONT_SMALL,
                     corner_radius=6).pack(fill="x", padx=10, pady=(2, 0))

        # === 信息显示 ===
        self._section(side, "坐标信息")
        self.info_text = ctk.CTkTextbox(side, height=100, font=("Consolas", 10),
                                        fg_color=THEME["card"])
        self.info_text.pack(fill="x", padx=10, pady=(0, 8))

        # === 右侧可视化 ===
        self._build_right_panel()

    def _add_empty_right(self):
        """无 pyproj 时的占位"""
        self.right_frame = ctk.CTkFrame(self, fg_color=THEME["card"])
        self.right_frame.grid(row=0, column=1, sticky="nsew")
        ctk.CTkLabel(self.right_frame, text="请安装 pyproj 后使用", font=FONT_NORMAL,
                    text_color=THEME["text_muted"]).place(relx=0.5, rely=0.5, anchor="center")

    def _build_right_panel(self):
        """构建右侧可视化区域"""
        self.coord_bar = ctk.CTkFrame(self, height=24, fg_color=THEME["statusbar"])
        self.coord_bar.grid(row=1, column=1, sticky="ew")
        self.coord_label = ctk.CTkLabel(self.coord_bar, text="", font=("Consolas", 10),
                                        text_color=THEME["text_secondary"])
        self.coord_label.pack(side="left", padx=10)

        # 点集 matplotlib
        self.point_frame = ctk.CTkFrame(self, fg_color=THEME["card"])
        self.point_frame.grid(row=0, column=1, sticky="nsew")
        self.fig, self.ax = plt.subplots(figsize=(6, 5))
        self.fig.patch.set_facecolor(THEME["card"])
        self.fig.subplots_adjust(left=0.12, right=0.95, top=0.93, bottom=0.12)
        self.point_canvas = FigureCanvasTkAgg(self.fig, self.point_frame)
        self.point_canvas.get_tk_widget().pack(fill="both", expand=True)
        self._draw_empty_points()

        # RasterViewer（初始隐藏）
        self.raster_viewer = RasterViewer(self, on_coord_change=self._on_raster_coord)
        self._view_mode = "points"

    def _on_raster_coord(self, text):
        self.coord_label.configure(text=text)

    def _show_points_view(self):
        self.raster_viewer.grid_forget()
        self.point_frame.grid(row=0, column=1, sticky="nsew")
        self.coord_label.configure(text="")
        self._view_mode = "points"

    def _show_raster_view(self):
        self.point_frame.grid_forget()
        self.raster_viewer.grid(row=0, column=1, sticky="nsew")
        self.raster_viewer.configure(fg_color=THEME["card"])
        self._view_mode = "raster"

    def _section(self, parent, text):
        ctk.CTkLabel(parent, text=text, font=FONT_SUBTITLE).pack(anchor="w", padx=14, pady=(8, 2))

    def _toggle_7param(self):
        if self.use7p.get():
            self.p7_frame.pack(fill="x", padx=0, pady=(0, 4))
        else:
            self.p7_frame.pack_forget()

    def _on_preset(self, choice):
        if choice == "自定义":
            return
        p = SevenParams.preset(choice)
        for k, v in [("dx", p.dx), ("dy", p.dy), ("dz", p.dz), ("rx", p.rx),
                      ("ry", p.ry), ("rz", p.rz), ("scale", p.scale)]:
            if k in self.p7_entries:
                self.p7_entries[k].delete(0, "end")
                self.p7_entries[k].insert(0, str(v))

    def _get_7params(self) -> SevenParams:
        if not self.use7p.get():
            return None
        try:
            return SevenParams(
                dx=float(self.p7_entries["dx"].get()),
                dy=float(self.p7_entries["dy"].get()),
                dz=float(self.p7_entries["dz"].get()),
                rx=float(self.p7_entries["rx"].get()),
                ry=float(self.p7_entries["ry"].get()),
                rz=float(self.p7_entries["rz"].get()),
                scale=float(self.p7_entries["scale"].get()),
            )
        except ValueError:
            return None

    # === 文件导入 ===
    def _load_points(self):
        path = filedialog.askopenfilename(
            title="导入点文件",
            filetypes=[("点文件", "*.csv *.txt *.xy *.pts"), ("所有文件", "*.*")]
        )
        if not path:
            return
        self.point_set = self.cs.parse_point_file(path)
        self.raster_info = None
        n = len(self.point_set.points)
        self.src_label.configure(text=f"点文件: {os.path.basename(path)} ({n} 个点)")
        self.info_text.delete("1.0", "end")
        self.info_text.insert("1.0", f"文件: {path}\n点数: {n}\n范围: {self._bbox_str()}")
        self._show_points_view()
        self._plot_points()

    @safe_execute
    def _load_raster(self):
        """导入影像（支持 GeoTIFF / PNG / JPG / BMP）"""
        path = filedialog.askopenfilename(
            title="导入影像",
            filetypes=[("影像", "*.tif *.tiff *.png *.jpg *.jpeg *.bmp *.img"), ("所有文件", "*.*")]
        )
        if not path:
            return
        # 先读取 CRS 信息（rasterio/Pillow 兜底）
        self.raster_info = self.cs.read_raster_info(path)
        self.point_set = PointSet()
        name = os.path.basename(path)
        crs_str = f"EPSG:{self.raster_info.epsg}" if self.raster_info.epsg else (self.raster_info.crs or "未知")
        self.src_label.configure(text=f"影像: {name} ({self.raster_info.width}x{self.raster_info.height})")
        self.info_text.delete("1.0", "end")
        self.info_text.insert("1.0",
            f"文件: {path}\n尺寸: {self.raster_info.width}x{self.raster_info.height}\n"
            f"波段: {self.raster_info.bands}\n坐标系: {crs_str}\n"
            f"范围: {self.raster_info.bounds}\n像素分辨率: {self.raster_info.pixel_size}")
        if self.raster_info.epsg:
            for k, v in {**COMMON_EPSG, **CHINA_EPSG}.items():
                if v == self.raster_info.epsg:
                    self.src_epsg.set(k)
                    break
        # 地理变换
        geo_t = None
        if self.raster_info.bounds != (0, 0, 0, 0) and self.raster_info.pixel_size != (1.0, 1.0):
            b = self.raster_info.bounds
            geo_t = (b[0], self.raster_info.pixel_size[0], 0,
                     b[3], 0, -self.raster_info.pixel_size[1])
        # 切换到栅格视图并显示影像
        self._show_raster_view()
        self.update_idletasks()  # 强制布局，确保canvas有尺寸
        try:
            self.raster_viewer.load(path, geo_transform=geo_t)
        except Exception:
            # 兜底：直接用 PIL 加载
            from PIL import Image
            import numpy as np
            im = Image.open(path).convert("RGB")
            arr = np.array(im)
            self.raster_viewer.load(image_array=arr, geo_transform=geo_t)

    def _bbox_str(self):
        if not self.point_set.points:
            return ""
        xs = [p[0] for p in self.point_set.points]
        ys = [p[1] for p in self.point_set.points]
        return f"X:[{min(xs):.4f}, {max(xs):.4f}]  Y:[{min(ys):.4f}, {max(ys):.4f}]"

    # === 点集可视化 ===
    def _draw_empty_points(self):
        self.ax.clear()
        self.ax.set_facecolor(THEME["card"])
        self.ax.text(0.5, 0.5, "导入点文件后显示", transform=self.ax.transAxes,
                    ha="center", va="center", fontsize=12, color=THEME["text_muted"])
        self.ax.set_xticks([])
        self.ax.set_yticks([])
        self.point_canvas.draw()

    def _plot_points(self, converted=None):
        self.ax.clear()
        self.ax.set_facecolor("#161822")
        self.ax.tick_params(colors=THEME["text_secondary"])
        for spine in self.ax.spines.values():
            spine.set_color(THEME["border"])

        pts = self.point_set.points
        if pts:
            xs, ys = zip(*pts)
            self.ax.scatter(xs, ys, c=THEME["accent"], s=30, zorder=5, label="原始坐标")
            names = self.point_set.names if self.point_set.names else [f"P{i+1}" for i in range(len(pts))]
            for i, (x, y) in enumerate(pts):
                self.ax.annotate(names[i] if i < len(names) else f"P{i+1}",
                                (x, y), textcoords="offset points", xytext=(4, 4),
                                fontsize=7, color=THEME["text_secondary"])

        if converted:
            cxs, cys = zip(*converted)
            self.ax.scatter(cxs, cys, c=THEME["success"], s=30, marker="s", zorder=5, label="转换结果")

        self.ax.legend(loc="upper right", fontsize=8)
        self.ax.set_xlabel("X / Lon", color=THEME["text_secondary"], fontsize=9)
        self.ax.set_ylabel("Y / Lat", color=THEME["text_secondary"], fontsize=9)
        self.ax.set_title(f"点集可视化 ({len(pts)} 点)", color=THEME["text_primary"], fontsize=11)
        self.ax.set_aspect("equal")
        self.point_canvas.draw()

    # === 执行与导出 ===
    def _execute(self):
        all_epsg = {**COMMON_EPSG, **CHINA_EPSG}
        src = all_epsg.get(self.src_epsg.get(), 4326)
        dst = all_epsg.get(self.dst_epsg.get(), 4526)
        params = self._get_7params()

        if self.point_set.points:
            converted = self.cs.transform_points(self.point_set.points, src, dst, params)
            if converted:
                info = f"转换完成: {len(converted)} 个点\n"
                info += f"源: {self.src_epsg.get()} (EPSG:{src})\n目标: {self.dst_epsg.get()} (EPSG:{dst})\n"
                if params:
                    info += f"7参数: dx={params.dx} dy={params.dy} dz={params.dz} rx={params.rx} ry={params.ry} rz={params.rz} s={params.scale}ppm\n"
                info += "\n前5个结果:\n"
                for s, d in zip(self.point_set.points[:5], converted[:5]):
                    info += f"  {s} -> {d}\n"
                self.info_text.delete("1.0", "end")
                self.info_text.insert("1.0", info)
                self._show_points_view()
                self._plot_points(converted)
                self._converted = converted
            else:
                messagebox.showerror("错误", "坐标转换失败")
        elif self.raster_info and self.raster_info.epsg:
            src = self.raster_info.epsg
            self.info_text.delete("1.0", "end")
            self.info_text.insert("1.0",
                f"影像坐标系已识别: EPSG:{src}\n目标坐标系: EPSG:{dst}\n"
                f"范围: {self.raster_info.bounds}\n"
                f"请使用命令行工具转换影像:\n"
                f"  pip install rasterio\n"
                f"  rio warp --dst-crs EPSG:{dst} input.tif output.tif")
        else:
            messagebox.showwarning("提示", "请先导入点文件或影像")

    def _export_csv(self):
        if not hasattr(self, "_converted") or not self._converted:
            messagebox.showwarning("提示", "请先执行转换")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV", "*.csv")],
            title="导出转换结果"
        )
        if path:
            all_epsg = {**COMMON_EPSG, **CHINA_EPSG}
            src = all_epsg.get(self.src_epsg.get(), 4326)
            dst = all_epsg.get(self.dst_epsg.get(), 4526)
            self.cs.export_points_csv(self.point_set.points, path, src, dst, self.point_set.names)
            messagebox.showinfo("成功",
                f"已导出 {len(self._converted)} 个点至:\n{path}")
