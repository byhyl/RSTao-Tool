"""Optional GPU acceleration helpers for point cloud processing.

The project must keep running on machines without CUDA, so GPU support is
strictly opt-in and always has a CPU fallback.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from functools import lru_cache
from typing import Any


@dataclass(frozen=True)
class GPUBackendStatus:
    backend: str = "cpu"
    available: bool = False
    device: str = ""
    reason: str = ""

    @property
    def label(self) -> str:
        if self.available:
            return f"{self.backend}: {self.device or 'available'}"
        return self.reason or "GPU unavailable"


@dataclass(frozen=True)
class NvidiaCudaInfo:
    nvidia_smi_found: bool = False
    cuda_version: str = ""
    driver_version: str = ""
    gpu_name: str = ""
    raw_output: str = ""
    reason: str = ""


@dataclass(frozen=True)
class GPUSetupPlan:
    status: GPUBackendStatus
    cuda_info: NvidiaCudaInfo
    recommended_package: str = ""
    pip_args: tuple[str, ...] = ()
    can_install: bool = False
    summary: str = ""
    steps: tuple[str, ...] = ()


@lru_cache(maxsize=4)
def get_gpu_status(preferred: str = "auto") -> GPUBackendStatus:
    """Return the currently usable GPU backend for array kernels.

    CuPy is used for point-cloud kernels because its ndarray API maps cleanly to
    the existing NumPy implementation. Torch CUDA can still be detected by other
    modules later, but this module reports it as unavailable for these kernels
    unless CuPy is present.
    """

    preferred = (preferred or "auto").lower()
    if preferred not in {"auto", "cupy", "cpu"}:
        preferred = "auto"
    if preferred == "cpu":
        return GPUBackendStatus(backend="cpu", available=False, reason="CPU mode")

    cupy_status = _cupy_status()
    if preferred == "cupy" or cupy_status.available:
        return cupy_status
    return GPUBackendStatus(
        backend="cpu",
        available=False,
        reason=cupy_status.reason or "CuPy/CUDA unavailable",
    )


def get_cupy(preferred: str = "auto") -> tuple[Any | None, GPUBackendStatus]:
    """Return (cupy_module, status) when CuPy CUDA kernels can be used."""

    status = get_gpu_status(preferred)
    if not status.available or status.backend != "cupy":
        return None, status
    try:
        import cupy as cp

        return cp, status
    except Exception as exc:  # pragma: no cover - depends on host CUDA stack.
        return None, GPUBackendStatus(
            backend="cpu",
            available=False,
            reason=f"CuPy import failed: {exc}",
        )


def gpu_available(preferred: str = "auto") -> bool:
    return get_gpu_status(preferred).available


def clear_gpu_status_cache() -> None:
    get_gpu_status.cache_clear()


def get_gpu_setup_plan() -> GPUSetupPlan:
    """Return a user-facing remediation plan for enabling CuPy/CUDA."""

    status = get_gpu_status("auto")
    cuda_info = detect_nvidia_cuda()
    if getattr(sys, "frozen", False):
        if status.available:
            return GPUSetupPlan(
                status=status,
                cuda_info=cuda_info,
                can_install=False,
                summary=f"GPU加速已可用：{status.label}",
                steps=("无需修复。",),
            )
        return GPUSetupPlan(
            status=status,
            cuda_info=cuda_info,
            can_install=False,
            summary="当前是打包版程序，不能在运行时安全安装新的 Python GPU 组件。",
            steps=(
                "请使用包含 CuPy 的 GPU 版安装包，或联系发布方重新打包 GPU 版。",
                "若使用源码/Conda 环境运行，可在该环境中安装 cupy-cuda12x 或 cupy-cuda13x。",
                "本程序会继续使用 CPU 后端，功能不受影响，只是速度较慢。",
            ),
        )

    if status.available:
        return GPUSetupPlan(
            status=status,
            cuda_info=cuda_info,
            can_install=False,
            summary=f"GPU加速已可用：{status.label}",
            steps=("无需修复。",),
        )

    if not cuda_info.nvidia_smi_found:
        return GPUSetupPlan(
            status=status,
            cuda_info=cuda_info,
            can_install=False,
            summary="未检测到 NVIDIA CUDA 驱动环境。",
            steps=(
                "请先安装或更新 NVIDIA 显卡驱动。",
                "安装驱动后重启电脑，再回到本程序点击“GPU修复”。",
                "没有 NVIDIA CUDA 显卡的设备会继续使用 CPU 后端。",
            ),
        )

    package = recommend_cupy_package(cuda_info.cuda_version)
    if not package:
        return GPUSetupPlan(
            status=status,
            cuda_info=cuda_info,
            can_install=False,
            summary=f"检测到 NVIDIA 驱动，但 CUDA {cuda_info.cuda_version or '未知'} 暂无自动方案。",
            steps=(
                "建议更新 NVIDIA 驱动到支持 CUDA 12 或 CUDA 13 的版本。",
                "也可以继续使用 CPU 后端运行 3D 处理。",
            ),
        )

    pip_args = build_cupy_install_command(package)
    return GPUSetupPlan(
        status=status,
        cuda_info=cuda_info,
        recommended_package=package,
        pip_args=pip_args,
        can_install=True,
        summary=f"检测到 CUDA {cuda_info.cuda_version}，可安装 {package} 启用 GPU 加速。",
        steps=(
            "程序将使用当前 Python 环境执行 pip 安装，不需要用户手动打开终端。",
            "安装完成后会自动复检 CuPy/CUDA 状态。",
            "若网络受限或驱动过旧，安装可能失败；失败时仍会保留 CPU 回退。",
        ),
    )


def format_gpu_setup_plan(plan: GPUSetupPlan) -> str:
    lines = [plan.summary]
    info = plan.cuda_info
    if info.gpu_name:
        lines.append(f"GPU：{info.gpu_name}")
    if info.driver_version:
        lines.append(f"驱动：{info.driver_version}")
    if info.cuda_version:
        lines.append(f"CUDA：{info.cuda_version}")
    if plan.recommended_package:
        lines.append(f"推荐包：{plan.recommended_package}")
    if plan.pip_args:
        lines.append("安装命令：" + " ".join(plan.pip_args))
    if plan.steps:
        lines.append("")
        lines.extend(f"- {step}" for step in plan.steps)
    if plan.status.reason and not plan.status.available:
        lines.append("")
        lines.append(f"当前不可用原因：{plan.status.reason}")
    return "\n".join(lines)


def detect_nvidia_cuda(timeout: float = 5.0) -> NvidiaCudaInfo:
    if shutil.which("nvidia-smi") is None:
        return NvidiaCudaInfo(reason="nvidia-smi not found")
    try:
        proc = subprocess.run(
            ["nvidia-smi"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except Exception as exc:
        return NvidiaCudaInfo(nvidia_smi_found=True, reason=str(exc))
    output = "\n".join(part for part in (proc.stdout, proc.stderr) if part)
    if proc.returncode != 0:
        return NvidiaCudaInfo(nvidia_smi_found=True, raw_output=output, reason=output.strip())
    parsed = parse_nvidia_smi_output(output)
    gpu_name = parsed.get("gpu_name", "")
    driver_version = parsed.get("driver_version", "")
    try:
        query = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if query.returncode == 0 and query.stdout.strip():
            first = query.stdout.strip().splitlines()[0]
            parts = [part.strip() for part in first.split(",", 1)]
            if parts:
                gpu_name = parts[0] or gpu_name
            if len(parts) > 1:
                driver_version = parts[1] or driver_version
    except Exception:
        pass
    return NvidiaCudaInfo(
        nvidia_smi_found=True,
        cuda_version=parsed.get("cuda_version", ""),
        driver_version=driver_version,
        gpu_name=gpu_name,
        raw_output=output,
    )


def parse_nvidia_smi_output(output: str) -> dict[str, str]:
    cuda_match = re.search(r"CUDA Version:\s*([0-9]+(?:\.[0-9]+)?)", output or "")
    driver_match = re.search(r"Driver Version:\s*([0-9.]+)", output or "")
    return {
        "cuda_version": cuda_match.group(1) if cuda_match else "",
        "driver_version": driver_match.group(1) if driver_match else "",
        "gpu_name": "",
    }


def recommend_cupy_package(cuda_version: str) -> str:
    """Return a CuPy wheel spec compatible with this project and the detected driver.

    The project currently pins NumPy < 2.0, so CuPy 13.x is the safe target.
    NVIDIA drivers that report CUDA 13 can still run CUDA 12 user-space
    components installed by the PyPI ``[ctk]`` extra.
    """

    match = re.match(r"\s*(\d+)", cuda_version or "")
    if not match:
        return ""
    major = int(match.group(1))
    if major >= 12:
        return "cupy-cuda12x[ctk]<14"
    return ""


def build_cupy_install_command(package_spec: str) -> tuple[str, ...]:
    if not package_spec:
        return ()
    return (sys.executable, "-m", "pip", "install", "-U", package_spec)


def _cupy_status() -> GPUBackendStatus:
    try:
        import cupy as cp

        count = int(cp.cuda.runtime.getDeviceCount())
        if count <= 0:
            return GPUBackendStatus(
                backend="cupy",
                available=False,
                reason="No CUDA device detected",
            )
        props = cp.cuda.runtime.getDeviceProperties(0)
        raw_name = props.get("name", b"")
        if isinstance(raw_name, bytes):
            device = raw_name.decode("utf-8", errors="ignore")
        else:
            device = str(raw_name)
        return GPUBackendStatus(backend="cupy", available=True, device=device)
    except Exception as exc:
        return GPUBackendStatus(
            backend="cupy",
            available=False,
            reason=f"CuPy/CUDA unavailable: {exc}",
        )
