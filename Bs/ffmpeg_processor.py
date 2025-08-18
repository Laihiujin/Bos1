import subprocess
import threading
import time
import signal
import os
from typing import Optional, Callable, Dict, Any

class FFmpegProcessor:
    """FFmpeg处理器，支持重试机制、超时控制和进程管理"""
    
    def __init__(self, max_retries=3, timeout=300):
        self.max_retries = max_retries
        self.timeout = timeout
        self.current_process = None
        self.is_cancelled = False
        self.process_lock = threading.Lock()
        
    def kill_stuck_ffmpeg_processes(self):
        """杀掉所有卡住的FFmpeg进程"""
        try:
            # 查找所有FFmpeg进程
            result = subprocess.run(
                ['ps', 'aux'], 
                capture_output=True, 
                text=True, 
                timeout=10
            )
            
            killed_count = 0
            for line in result.stdout.split('\n'):
                if 'ffmpeg' in line and 'grep' not in line:
                    parts = line.split()
                    if len(parts) > 1:
                        try:
                            pid = int(parts[1])
                            # 检查进程运行时间，只杀掉运行时间过长且可能卡住的进程
                            # 获取进程启动时间（ps aux格式中的STAT字段后面是START时间）
                            if len(parts) > 8:  # 确保有足够的字段
                                # 只杀掉明显异常的进程（比如运行超过1小时的）
                                # 这里我们采用更保守的策略，只在明确需要时才杀进程
                                # 暂时注释掉自动杀进程的逻辑，避免误杀
                                print(f"🔍 发现FFmpeg进程 PID: {pid}，暂不自动终止")
                                # os.kill(pid, signal.SIGKILL)
                                # killed_count += 1
                                # print(f"🔪 终止可能卡住的FFmpeg进程 PID: {pid}")
                        except (ValueError, ProcessLookupError, PermissionError):
                            continue
                            
            return killed_count
            
        except Exception as e:
            print(f"❌ 清理FFmpeg进程时出错: {e}")
            return 0
    
    def cancel_current_process(self):
        """取消当前正在运行的FFmpeg进程"""
        with self.process_lock:
            self.is_cancelled = True
            if self.current_process and self.current_process.poll() is None:
                try:
                    self.current_process.terminate()
                    # 等待2秒，如果还没结束就强制杀掉
                    time.sleep(2)
                    if self.current_process.poll() is None:
                        self.current_process.kill()
                    print("🛑 已取消当前FFmpeg进程")
                    return True
                except Exception as e:
                    print(f"❌ 取消进程时出错: {e}")
                    return False
        return False
    
    def process_with_retry(self, command, progress_callback=None):
        """带重试机制的FFmpeg执行"""
        self.is_cancelled = False
        
        # 保存当前命令，供超时监控使用
        self.current_command = command
        
        for attempt in range(self.max_retries):
            if self.is_cancelled:
                print("🛑 处理已被取消")
                self.current_command = None  # 清除命令引用
                return False, "处理已被用户取消"
                
            try:
                print(f"🔄 尝试 {attempt + 1}/{self.max_retries}")
                
                # 在每次重试前清理卡住的进程
                if attempt > 0:
                    killed = self.kill_stuck_ffmpeg_processes()
                    if killed > 0:
                        print(f"🧹 清理了 {killed} 个卡住的FFmpeg进程")
                        time.sleep(2)  # 等待系统清理
                
                success, message = self._execute_ffmpeg(command, progress_callback)
                
                if success:
                    self.current_command = None  # 清除命令引用
                    return True, "处理成功完成"
                elif self.is_cancelled:
                    self.current_command = None  # 清除命令引用
                    return False, "处理已被取消"
                else:
                    print(f"❌ 尝试 {attempt + 1} 失败: {message}")
                    if attempt < self.max_retries - 1:
                        wait_time = 2 ** attempt  # 指数退避
                        print(f"⏳ 等待 {wait_time} 秒后重试...")
                        time.sleep(wait_time)
                        
            except Exception as e:
                print(f"❌ 尝试 {attempt + 1} 出现异常: {e}")
                if attempt == self.max_retries - 1:
                    self.current_command = None  # 清除命令引用
                    return False, f"所有重试都失败了: {e}"
                    
        self.current_command = None  # 清除命令引用
        return False, f"经过 {self.max_retries} 次重试后仍然失败"
    
    def _execute_ffmpeg(self, command, progress_callback=None):
        """执行FFmpeg命令"""
        try:
            with self.process_lock:
                if self.is_cancelled:
                    return False, "处理已被取消"
                    
                # 记录进程启动时间
                self.process_start_time = time.time()
                
                # 启动FFmpeg进程
                self.current_process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True,
                    encoding='utf-8',
                    errors='ignore',  # 忽略无法解码的字符
                    bufsize=1
                )
            
            # 使用线程监控超时
            timeout_thread = threading.Thread(
                target=self._timeout_monitor,
                args=(self.current_process,)
            )
            timeout_thread.daemon = True
            timeout_thread.start()
            
            # 模拟进度更新（简化版本，避免复杂的输出解析）
            if progress_callback:
                progress_thread = threading.Thread(
                    target=self._simulate_progress,
                    args=(progress_callback,)
                )
                progress_thread.daemon = True
                progress_thread.start()
            
            # 等待进程完成
            stdout, stderr = self.current_process.communicate()
            
            if self.is_cancelled:
                return False, "处理已被取消"
                
            if self.current_process.returncode == 0:
                # 确保进度回调显示100%完成
                if progress_callback:
                    progress_callback(100, "处理完成")
                return True, "FFmpeg执行成功"
            else:
                # 提供更详细的错误信息
                error_msg = stderr.strip() if stderr else "未知错误"
                # 提取关键错误信息
                if "No such file or directory" in error_msg:
                    return False, "文件不存在或路径错误"
                elif "Invalid data found" in error_msg:
                    return False, "视频文件损坏或格式不支持"
                elif "Permission denied" in error_msg:
                    return False, "文件权限不足"
                elif "Disk full" in error_msg or "No space left" in error_msg:
                    return False, "磁盘空间不足"
                else:
                    return False, f"FFmpeg执行失败: {error_msg[:200]}..." if len(error_msg) > 200 else f"FFmpeg执行失败: {error_msg}"
                
        except subprocess.TimeoutExpired:
            return False, "FFmpeg执行超时"
        except Exception as e:
            return False, f"FFmpeg执行异常: {e}"
        finally:
            with self.process_lock:
                self.current_process = None
                self.process_start_time = None
    
    def _timeout_monitor(self, process):
        """超时监控线程 - 增强版，定期检查进程状态和资源使用"""
        start_time = time.time()
        check_interval = 10  # 每10秒检查一次（原为15秒）
        last_progress_time = start_time
        last_output_size = 0
        stalled_count = 0
        max_stalled_checks = 3  # 连续3次检查无进展则视为卡住（原为4次）
        cpu_usage_samples = []  # CPU使用率样本
        
        # 获取输出文件路径（如果可能）
        output_path = None
        if hasattr(self, 'current_command') and self.current_command:
            for i, arg in enumerate(self.current_command):
                if arg == '-y' and i+1 < len(self.current_command):
                    output_path = self.current_command[i+1]
                    break
        
        while True:
            # 如果进程已结束或被取消，退出监控
            if not process or process.poll() is not None or self.is_cancelled:
                return
                
            current_time = time.time()
            elapsed_time = current_time - start_time
            
            # 检查是否超时
            if elapsed_time >= self.timeout:
                print(f"⏰ FFmpeg进程超时 ({self.timeout}秒)，正在终止...")
                try:
                    # 先尝试正常终止
                    process.terminate()
                    
                    # 等待最多5秒看进程是否结束
                    for _ in range(5):
                        time.sleep(1)
                        if process.poll() is not None:
                            print("进程已正常终止")
                            break
                    
                    # 如果进程仍未结束，强制杀死
                    if process.poll() is None:
                        print("进程未响应终止信号，强制结束...")
                        process.kill()
                        
                        # 再等待3秒确认进程已被杀死
                        for _ in range(3):
                            time.sleep(1)
                            if process.poll() is not None:
                                print("进程已被强制终止")
                                break
                        
                        # 如果进程仍未结束，尝试使用系统命令杀死
                        if process.poll() is None:
                            print("进程仍未终止，尝试使用系统命令强制终止...")
                            try:
                                import signal
                                os.kill(process.pid, signal.SIGKILL)
                            except Exception as e:
                                print(f"使用系统命令终止进程时出错: {e}")
                except Exception as e:
                    print(f"终止进程时出错: {e}")
                    
                # 清理相关资源
                with self.process_lock:
                    self.current_process = None
                return
            
            # 检查进程资源使用情况
            try:
                import psutil
                proc = psutil.Process(process.pid)
                cpu_percent = proc.cpu_percent(interval=0.5)
                memory_percent = proc.memory_percent()
                cpu_usage_samples.append(cpu_percent)
                
                # 保留最近5个样本
                if len(cpu_usage_samples) > 5:
                    cpu_usage_samples.pop(0)
                
                # 计算平均CPU使用率
                avg_cpu = sum(cpu_usage_samples) / len(cpu_usage_samples) if cpu_usage_samples else 0
                
                # 如果CPU使用率持续过低且进程运行超过30秒，可能卡住了
                if elapsed_time > 30 and avg_cpu < 1.0 and len(cpu_usage_samples) >= 3:
                    print(f"警告: CPU使用率过低 ({avg_cpu:.1f}%)，可能卡住")
                    stalled_count += 1
                    if stalled_count >= max_stalled_checks:  # 连续多次检测到低CPU使用率
                        print(f"⚠️ FFmpeg进程CPU使用率持续过低，可能卡住，正在终止...")
                        try:
                            process.terminate()
                            time.sleep(2)
                            if process.poll() is None:
                                process.kill()
                        except Exception as e:
                            print(f"终止卡住进程时出错: {e}")
                        return
            except (ImportError, Exception) as e:
                # psutil可能未安装或进程访问出错
                pass
            
            # 检查输出文件大小是否有变化（判断进程是否卡住）
            if output_path and os.path.exists(output_path):
                try:
                    current_size = os.path.getsize(output_path)
                    if current_size == last_output_size:
                        stalled_count += 1
                        print(f"警告: 输出文件大小未变化 ({stalled_count}/{max_stalled_checks})")
                        if stalled_count >= max_stalled_checks:
                            print(f"⚠️ FFmpeg进程似乎卡住了（输出文件大小长时间未变化），正在终止...")
                            try:
                                process.terminate()
                                time.sleep(2)
                                if process.poll() is None:
                                    process.kill()
                            except Exception as e:
                                print(f"终止卡住进程时出错: {e}")
                            return
                    else:
                        stalled_count = 0  # 重置卡住计数
                        print(f"✅ 输出文件大小正常增长: {last_output_size} -> {current_size} bytes")
                    last_output_size = current_size
                    
                    # 检查文件大小增长率和进程运行时间
                    if elapsed_time > 120:  # 运行超过2分钟
                        # 如果文件过小，可能卡住了
                        if current_size < 1024 * 1024:  # 文件小于1MB
                            print(f"⚠️ 进程运行{elapsed_time:.1f}秒，但输出文件仅{current_size/1024:.1f}KB，可能卡住，终止进程")
                            try:
                                process.terminate()
                                time.sleep(2)
                                if process.poll() is None:
                                    process.kill()
                            except Exception as e:
                                print(f"终止卡住进程时出错: {e}")
                            return
                        
                        # 如果文件大小增长率过低，也可能卡住了
                        if elapsed_time > 300 and last_output_size > 0:  # 运行超过5分钟且有上次大小记录
                            # 计算每秒平均增长字节数
                            growth_rate = (current_size - last_output_size) / check_interval
                            if growth_rate < 10240:  # 每秒增长少于10KB
                                print(f"⚠️ 文件增长率过低 ({growth_rate:.1f} bytes/s)，可能卡住，终止进程")
                                try:
                                    process.terminate()
                                    time.sleep(2)
                                    if process.poll() is None:
                                        process.kill()
                                except Exception as e:
                                    print(f"终止卡住进程时出错: {e}")
                                return
                except Exception as e:
                    print(f"检查输出文件时出错: {e}")
            
            # 短暂休眠后继续检查
            time.sleep(check_interval)
    
    def _simulate_progress(self, progress_callback):
        """模拟进度更新 - 改进版，更平滑的进度过渡"""
        progress = 0
        start_time = time.time()
        last_update_time = start_time
        slow_progress_threshold = 90  # 90%后进度变慢
        
        # 快速阶段 - 0% 到 90%
        while progress < slow_progress_threshold and not self.is_cancelled:
            if self.current_process and self.current_process.poll() is not None:
                # 进程已结束
                if self.current_process.returncode == 0:
                    progress_callback(100, "处理完成")
                else:
                    progress_callback(progress, f"处理失败 (退出码: {self.current_process.returncode})")
                return
                
            # 快速增长阶段
            progress = min(progress + 5, slow_progress_threshold)
            progress_callback(progress, f"处理中... {progress}%")
            time.sleep(0.8)  # 更新间隔
        
        # 慢速阶段 - 90% 到 98%
        while progress < 98 and not self.is_cancelled:
            if self.current_process and self.current_process.poll() is not None:
                # 进程已结束
                if self.current_process.returncode == 0:
                    progress_callback(100, "处理完成")
                else:
                    progress_callback(progress, f"处理失败 (退出码: {self.current_process.returncode})")
                return
            
            # 慢速增长阶段
            current_time = time.time()
            if current_time - last_update_time >= 3:  # 每3秒更新一次
                progress = min(progress + 1, 98)
                progress_callback(progress, f"处理中... {progress}%")
                last_update_time = current_time
            
            time.sleep(1)  # 更频繁地检查进程状态
            
        # 等待进程完成
        if not self.is_cancelled and self.current_process:
            check_interval = 0.5  # 检查间隔
            last_status_time = time.time()
            max_wait_time = 60  # 最大等待时间60秒
            wait_start_time = time.time()
            
            # 等待进程完成
            while self.current_process and self.current_process.poll() is None and not self.is_cancelled:
                current_time = time.time()
                
                # 检查是否等待时间过长
                if current_time - wait_start_time > max_wait_time:
                    progress_callback(99, "处理超时，正在强制完成...")
                    break
                
                # 每10秒更新一次状态，让用户知道进程仍在运行
                if current_time - last_status_time >= 10:
                    progress_callback(98, f"处理中... 98% (正在完成最终处理)")
                    last_status_time = current_time
                
                time.sleep(check_interval)
            
            # 进程完成后的最终状态更新
            if self.current_process and self.current_process.poll() is not None:
                if self.current_process.returncode == 0:
                    progress_callback(100, "处理完成")
                else:
                    progress_callback(99, f"处理失败 (退出码: {self.current_process.returncode})")
            elif self.is_cancelled:
                progress_callback(0, "处理已取消")
            else:
                progress_callback(100, "处理完成")
    
    def get_status(self):
        """获取当前处理状态，增强版，可以检测卡住的进程"""
        with self.process_lock:
            if self.current_process is None:
                return "空闲"
            elif self.current_process.poll() is None:
                # 检查是否有输出文件且大小长时间未变化
                if hasattr(self, 'current_command') and self.current_command:
                    output_path = None
                    for i, arg in enumerate(self.current_command):
                        if arg == '-y' and i+1 < len(self.current_command):
                            output_path = self.current_command[i+1]
                            break
                    
                    if output_path and os.path.exists(output_path):
                        # 检查进程运行时间
                        if hasattr(self, 'process_start_time'):
                            elapsed_time = time.time() - self.process_start_time
                            # 如果进程运行超过5分钟，且输出文件存在但大小小于1MB，可能卡住了
                            if elapsed_time > 300 and os.path.getsize(output_path) < 1024 * 1024:
                                return "卡住"
                
                return "运行中"
            else:
                return "已完成"