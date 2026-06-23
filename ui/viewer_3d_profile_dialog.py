"""Profile / cross-section chart dialog for 3D viewer."""

from __future__ import annotations

from pathlib import Path

import customtkinter as ctk
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from .theme import FONT_SMALL, THEME

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


class ProfileDialog(ctk.CTkToplevel):
    """Display a distance-elevation profile chart from SectionTool data."""

    def __init__(
        self, parent, distances: np.ndarray, elevations: np.ndarray, title: str = "剖面分析"
    ):
        super().__init__(parent)
        self.title(title)
        self.geometry("700x420")
        self.minsize(500, 300)
        self.configure(fg_color=THEME["bg"])
        self.transient(parent.winfo_toplevel())

        self._distances = distances
        self._elevations = elevations
        self._build_ui()

    def _build_ui(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(12, 4))

        if len(self._distances) > 0:
            d_total = self._distances[-1]
            z_min = float(np.nanmin(self._elevations))
            z_max = float(np.nanmax(self._elevations))
            z_diff = z_max - z_min
            stats_text = (
                f"剖面长度: {d_total:.2f} m | "
                f"最低: {z_min:.2f} m | "
                f"最高: {z_max:.2f} m | "
                f"高差: {z_diff:.2f} m"
            )
        else:
            stats_text = "无剖面数据"

        ctk.CTkLabel(
            header,
            text=stats_text,
            font=FONT_SMALL,
            text_color=THEME["text_secondary"],
            anchor="w",
        ).pack(fill="x")

        fig = Figure(figsize=(6.5, 3), dpi=100, facecolor=THEME["card"])
        ax = fig.add_subplot(111)
        ax.set_facecolor(THEME["card"])
        ax.tick_params(colors=THEME["text_secondary"], labelsize=8)
        ax.spines["bottom"].set_color(THEME["border"])
        ax.spines["left"].set_color(THEME["border"])
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

        if len(self._distances) > 0:
            ax.fill_between(
                self._distances,
                self._elevations,
                self._elevations.min() - 5,
                alpha=0.3,
                color="#4cc9f0",
            )
            ax.plot(self._distances, self._elevations, color="#4cc9f0", linewidth=1.2)
            ax.set_xlabel("距离 (m)", fontsize=9, color=THEME["text_secondary"])
            ax.set_ylabel("高程 (m)", fontsize=9, color=THEME["text_secondary"])
        else:
            ax.text(
                0.5,
                0.5,
                "无数据",
                transform=ax.transAxes,
                ha="center",
                va="center",
                color=THEME["text_muted"],
            )

        canvas = FigureCanvasTkAgg(fig, master=self)
        canvas.get_tk_widget().pack(fill="both", expand=True, padx=16, pady=(0, 12))

        export_row = ctk.CTkFrame(self, fg_color="transparent")
        export_row.pack(fill="x", padx=16, pady=(0, 12))
        ctk.CTkButton(
            export_row,
            text="导出CSV",
            width=90,
            height=28,
            font=("Microsoft YaHei UI", 11),
            fg_color=THEME["accent"],
            hover_color=THEME["accent_hover"],
            command=self._export_csv,
        ).pack(side="right", padx=4)
        ctk.CTkButton(
            export_row,
            text="复制图表",
            width=90,
            height=28,
            font=("Microsoft YaHei UI", 11),
            fg_color="transparent",
            border_width=1,
            border_color=THEME["border"],
            text_color=THEME["text_primary"],
            hover_color=THEME["hover"],
            command=self._copy_chart,
        ).pack(side="right", padx=4)

    def _export_csv(self):
        from tkinter import filedialog

        path = filedialog.asksaveasfilename(
            title="导出剖面CSV",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
        )
        if not path:
            return
        data = np.column_stack([self._distances, self._elevations])
        np.savetxt(path, data, delimiter=",", header="distance,elevation", comments="", fmt="%.3f")

    def _copy_chart(self):
        import io

        try:
            import pyperclip

            buf = io.BytesIO()
            plt.figure(figsize=(8, 4), dpi=150)
            plt.fill_between(
                self._distances,
                self._elevations,
                self._elevations.min() - 5,
                alpha=0.3,
                color="#4cc9f0",
            )
            plt.plot(self._distances, self._elevations, color="#4cc9f0", linewidth=1.2)
            plt.xlabel("距离 (m)")
            plt.ylabel("高程 (m)")
            plt.tight_layout()
            plt.savefig(buf, format="png")
            plt.close()
            buf.seek(0)
            from PIL import Image

            img = Image.open(buf)
            import io as io2

            output = io2.BytesIO()
            img.convert("RGB").save(output, format="BMP")
            pyperclip.copy(output.getvalue())
        except ImportError:
            pass
