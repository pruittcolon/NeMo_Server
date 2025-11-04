"""
GPU Monitor
Tracks GPU VRAM usage via nvidia-smi
"""

import subprocess
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class GPUMonitor:
    """Monitor GPU memory and utilization"""
    
    def __init__(self, gpu_id: int = 0):
        """
        Initialize GPU monitor
        
        Args:
            gpu_id: GPU device ID (default: 0)
        """
        self.gpu_id = gpu_id
        self.available = self._check_nvidia_smi()
    
    def _check_nvidia_smi(self) -> bool:
        """Check if nvidia-smi is available"""
        try:
            subprocess.run(
                ["nvidia-smi", "--version"],
                capture_output=True,
                check=True,
                timeout=2
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            logger.warning("nvidia-smi not available - GPU monitoring disabled")
            return False
    
    def get_vram_usage(self) -> Optional[Dict[str, int]]:
        """
        Get current VRAM usage
        
        Returns:
            Dictionary with used_mb and total_mb, or None if unavailable
        """
        if not self.available:
            return None
        
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    f"--id={self.gpu_id}",
                    "--query-gpu=memory.used,memory.total",
                    "--format=csv,noheader,nounits"
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=2
            )
            
            used, total = result.stdout.strip().split(',')
            
            return {
                "used_mb": int(used.strip()),
                "total_mb": int(total.strip()),
                "free_mb": int(total.strip()) - int(used.strip()),
                "utilization_pct": round((int(used.strip()) / int(total.strip())) * 100, 1)
            }
            
        except Exception as e:
            logger.error(f"Failed to get VRAM usage: {e}")
            return None
    
    def get_gpu_utilization(self) -> Optional[int]:
        """
        Get GPU compute utilization percentage
        
        Returns:
            Utilization percentage (0-100), or None if unavailable
        """
        if not self.available:
            return None
        
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    f"--id={self.gpu_id}",
                    "--query-gpu=utilization.gpu",
                    "--format=csv,noheader,nounits"
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=2
            )
            
            return int(result.stdout.strip())
            
        except Exception as e:
            logger.error(f"Failed to get GPU utilization: {e}")
            return None
    
    def get_running_processes(self) -> List[Dict[str, str]]:
        """
        Get list of processes using the GPU
        
        Returns:
            List of process dictionaries with pid, name, used_memory
        """
        if not self.available:
            return []
        
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    f"--id={self.gpu_id}",
                    "--query-compute-apps=pid,name,used_memory",
                    "--format=csv,noheader,nounits"
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=2
            )
            
            processes = []
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    parts = line.split(',')
                    if len(parts) >= 3:
                        processes.append({
                            "pid": parts[0].strip(),
                            "name": parts[1].strip(),
                            "used_memory_mb": parts[2].strip()
                        })
            
            return processes
            
        except Exception as e:
            logger.error(f"Failed to get GPU processes: {e}")
            return []
    
    def get_full_status(self) -> Dict[str, any]:
        """
        Get comprehensive GPU status
        
        Returns:
            Full status dictionary
        """
        vram = self.get_vram_usage()
        utilization = self.get_gpu_utilization()
        processes = self.get_running_processes()
        
        return {
            "gpu_id": self.gpu_id,
            "available": self.available,
            "vram": vram,
            "utilization_pct": utilization,
            "processes": processes,
            "process_count": len(processes)
        }


# Singleton instance
_monitor: Optional[GPUMonitor] = None


def get_gpu_monitor() -> GPUMonitor:
    """Get or create GPU monitor singleton"""
    global _monitor
    if _monitor is None:
        _monitor = GPUMonitor()
    return _monitor







