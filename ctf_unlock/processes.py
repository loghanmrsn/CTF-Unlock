"""Sous-processus bornés, sans shell, avec arrêt de groupe / Job Object Windows."""
from dataclasses import dataclass
import os
import signal
import subprocess
import tempfile
import time
from typing import Callable


class Aborted(Exception):
    pass


class ResourceError(RuntimeError):
    pass


class WindowsJob:
    def __init__(self, process, memory_mb):
        import ctypes as c
        from ctypes import wintypes as w
        class Basic(c.Structure):
            _fields_ = [('process_time', c.c_longlong), ('job_time', c.c_longlong), ('flags', w.DWORD),
                        ('min_ws', c.c_size_t), ('max_ws', c.c_size_t), ('active', w.DWORD),
                        ('affinity', c.c_size_t), ('priority', w.DWORD), ('scheduling', w.DWORD)]
        class IO(c.Structure):
            _fields_ = [(name, c.c_ulonglong) for name in ['read_ops', 'write_ops', 'other_ops', 'read_bytes', 'write_bytes', 'other_bytes']]
        class Extended(c.Structure):
            _fields_ = [('basic', Basic), ('io', IO), ('process_memory', c.c_size_t),
                        ('job_memory', c.c_size_t), ('peak_process', c.c_size_t), ('peak_job', c.c_size_t)]
        self.kernel = c.WinDLL('kernel32', use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = [c.c_void_p, w.LPCWSTR]
        self.kernel.CreateJobObjectW.restype = w.HANDLE
        self.kernel.SetInformationJobObject.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD]
        self.kernel.SetInformationJobObject.restype = w.BOOL
        self.kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        self.kernel.AssignProcessToJobObject.restype = w.BOOL
        self.kernel.TerminateJobObject.argtypes = [w.HANDLE, w.UINT]
        self.kernel.TerminateJobObject.restype = w.BOOL
        self.kernel.CloseHandle.argtypes = [w.HANDLE]
        self.kernel.CloseHandle.restype = w.BOOL
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ResourceError(f'Job Object Windows indisponible : {c.get_last_error()}')
        limits = Extended()
        limits.basic.flags = 0x2000 | 0x200  # kill-on-close et mémoire totale du job.
        limits.job_memory = memory_mb * 1024 * 1024
        configured = self.kernel.SetInformationJobObject(self.handle, 9, c.byref(limits), c.sizeof(limits))
        assigned = configured and self.kernel.AssignProcessToJobObject(self.handle, int(process._handle))
        # Windows peut refuser l'attachement d'un programme déjà en cours de sortie,
        # avant que GetExitCodeProcess ne signale effectivement sa fin.
        if configured and not assigned and process.poll() is None:
            try:
                process.wait(timeout=.05)
            except subprocess.TimeoutExpired:
                pass
        if not configured or (not assigned and process.poll() is None):
            error = c.get_last_error()
            self.close()
            raise ResourceError(f'Impossible d’appliquer les limites Windows (code {error}). Aucun essai poursuivi.')

    def kill(self):
        self.kernel.TerminateJobObject(self.handle, 1)

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def resume_windows_process(process):
    """Reprend le thread initial après affectation au Job Object, avant tout code moteur."""
    import ctypes as c
    from ctypes import wintypes as w
    class ThreadEntry(c.Structure):
        _fields_ = [('size', w.DWORD), ('usage', w.DWORD), ('thread_id', w.DWORD),
                    ('owner_pid', w.DWORD), ('base_priority', w.LONG), ('delta_priority', w.LONG), ('flags', w.DWORD)]
    kernel = c.WinDLL('kernel32', use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [w.DWORD, w.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = w.HANDLE
    kernel.Thread32First.argtypes = [w.HANDLE, c.POINTER(ThreadEntry)]
    kernel.Thread32First.restype = w.BOOL
    kernel.Thread32Next.argtypes = [w.HANDLE, c.POINTER(ThreadEntry)]
    kernel.Thread32Next.restype = w.BOOL
    kernel.OpenThread.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    kernel.OpenThread.restype = w.HANDLE
    kernel.ResumeThread.argtypes = [w.HANDLE]
    kernel.ResumeThread.restype = w.DWORD
    kernel.CloseHandle.argtypes = [w.HANDLE]
    snapshot = kernel.CreateToolhelp32Snapshot(4, 0)  # TH32CS_SNAPTHREAD
    if snapshot == c.c_void_p(-1).value:
        raise ResourceError('Impossible d’énumérer le thread suspendu du moteur Windows.')
    try:
        entry = ThreadEntry()
        entry.size = c.sizeof(entry)
        available = kernel.Thread32First(snapshot, c.byref(entry))
        while available:
            if entry.owner_pid == process.pid:
                thread = kernel.OpenThread(2, False, entry.thread_id)  # THREAD_SUSPEND_RESUME
                if not thread:
                    raise ResourceError('Impossible d’ouvrir le thread initial du moteur.')
                try:
                    if kernel.ResumeThread(thread) == 0xffffffff:
                        raise ResourceError('Impossible de reprendre le moteur Windows limité.')
                    return
                finally:
                    kernel.CloseHandle(thread)
            available = kernel.Thread32Next(snapshot, c.byref(entry))
        raise ResourceError('Thread initial du moteur Windows introuvable.')
    finally:
        kernel.CloseHandle(snapshot)


@dataclass(frozen=True)
class CommandResult:
    code: int
    output: str


def run(arguments: list[str], *, timeout: float, memory_mb: int = 512,
        abort: Callable[[], str | None] = lambda: None, env: dict | None = None,
        heartbeat: Callable[[], None] | None = None) -> CommandResult:
    reason = abort()
    if reason:
        raise Aborted(reason)
    options = {'creationflags': subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP | 0x4} if os.name == 'nt' else {'start_new_session': True}
    job = None
    with tempfile.TemporaryFile() as capture:
        process = subprocess.Popen(arguments, stdin=subprocess.DEVNULL, stdout=capture, stderr=subprocess.STDOUT,
                                   shell=False, env={**os.environ, **(env or {})}, **options)
        def terminate():
            if job:
                job.kill()
            elif os.name == 'posix':
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            elif process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=.5)
            except subprocess.TimeoutExpired:
                if os.name == 'posix':
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                else:
                    process.kill()
                process.wait(timeout=2)
        try:
            if os.name == 'nt':
                job = WindowsJob(process, memory_mb)
                resume_windows_process(process)
            elif os.name == 'posix':
                import resource
                try:
                    resource.prlimit(process.pid, resource.RLIMIT_AS, (memory_mb * 1024 * 1024,) * 2)
                except ProcessLookupError:
                    pass  # Le processus a déjà fini ; rien ne reste à limiter.
                except (OSError, AttributeError) as exc:
                    raise ResourceError(f'Limite mémoire non disponible : {exc}') from exc
            else:
                raise ResourceError('Plateforme non prise en charge pour les limites de processus.')
            deadline = time.monotonic() + timeout
            next_heartbeat = 0.0
            while process.poll() is None:
                reason = abort()
                if reason:
                    raise Aborted(reason)
                if time.monotonic() >= deadline:
                    raise Aborted('Délai par opération moteur atteint.')
                if os.fstat(capture.fileno()).st_size > 1024 * 1024:
                    raise ResourceError('Sortie moteur trop volumineuse (limite 1 Mio).')
                if heartbeat and time.monotonic() >= next_heartbeat:
                    heartbeat()
                    next_heartbeat = time.monotonic() + .25
                time.sleep(.02)
            if os.fstat(capture.fileno()).st_size > 1024 * 1024:
                raise ResourceError('Sortie moteur trop volumineuse (limite 1 Mio).')
            capture.seek(0)
            return CommandResult(process.returncode, capture.read(1024 * 1024).decode('utf-8', errors='replace'))
        finally:
            terminate()
            if job:
                job.close()
