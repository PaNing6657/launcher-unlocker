import argparse
import ctypes
import os
import struct
import subprocess
import sys
import time
from ctypes import wintypes as wt


def _geo_stub() -> bytes:
    b = bytearray()
    b += bytes.fromhex("4885c9")
    jz_at = len(b); b += b"\x74\x00"
    b += bytes.fromhex("83fa03")
    jl_at = len(b); b += b"\x7c\x00"
    b += bytes.fromhex("c70155005300")
    b += bytes.fromhex("66c741040000")
    b += bytes.fromhex("b803000000")        # 返回含结尾 NUL 的字符数 3
    b += bytes.fromhex("c3")
    fail = len(b)
    b += bytes.fromhex("33c0c3")
    b[jz_at + 1] = (fail - (jz_at + 2)) & 0xFF
    b[jl_at + 1] = (fail - (jl_at + 2)) & 0xFF
    return bytes(b)


def _geoid_stub() -> bytes:
    """GetUserGeoID 返回美国 GeoID 244。"""
    return bytes.fromhex("b8f4000000c3")

STUB_GEO_X64 = _geo_stub()
STUB_GEOID_X64 = _geoid_stub()


def _locale_stub() -> bytes:
    b = bytearray()
    b += bytes.fromhex("4885c9")
    jz_at = len(b); b += b"\x74\x00"
    b += bytes.fromhex("83fa06")
    jl_at = len(b); b += b"\x7c\x00"
    for i, ch in enumerate("en-US"):
        if i == 0:
            b += bytes.fromhex("66c701") + ch.encode("utf-16-le")
        else:
            b += bytes.fromhex("66c741") + bytes([i * 2]) + ch.encode("utf-16-le")
    b += bytes.fromhex("66c7410a0000")
    b += bytes.fromhex("b806000000")        # 返回含结尾 NUL 的字符数 6
    b += bytes.fromhex("c3")
    fail = len(b)
    b += bytes.fromhex("33c0c3")
    b[jz_at + 1] = (fail - (jz_at + 2)) & 0xFF
    b[jl_at + 1] = (fail - (jl_at + 2)) & 0xFF
    return bytes(b)

STUB_LOCALE_X64 = _locale_stub()

STUB_LCID_X64 = bytes.fromhex("b809040000c3")


def _tz_stub(nbytes: int) -> bytes:
    b = bytearray()
    b += bytes.fromhex("4885c9")
    jz_at = len(b); b += b"\x74\x00"
    b += bytes.fromhex("5756")
    b += bytes.fromhex("488bf9")
    b += b"\x48\xbe" + MARK8 * 8
    b += b"\xb9" + struct.pack("<I", nbytes)
    b += bytes.fromhex("f3a4")
    b += bytes.fromhex("5e5f")
    b += bytes.fromhex("b801000000")
    b += bytes.fromhex("c3")
    fail = len(b)
    b += bytes.fromhex("33c0c3")
    b[jz_at + 1] = (fail - (jz_at + 2)) & 0xFF
    return bytes(b)


def _kbl_list_stub() -> bytes:
    b = bytearray()
    b += bytes.fromhex("4885d2")
    jz = len(b); b += b"\x74\x00"
    b += bytes.fromhex("85c9")
    jz2 = len(b); b += b"\x74\x00"
    b += bytes.fromhex("48c702") + struct.pack("<I", HKL_EN_US)
    b += bytes.fromhex("b801000000")
    b += bytes.fromhex("c3")
    one = len(b)
    b += bytes.fromhex("b801000000")
    b += bytes.fromhex("c3")
    b[jz + 1] = (one - (jz + 2)) & 0xFF
    b[jz2 + 1] = (one - (jz2 + 2)) & 0xFF
    return bytes(b)


def _uilang_stub() -> bytes:
    b = bytearray()
    b += bytes.fromhex("4885d2")                      # test rdx, rdx
    jz = len(b); b += b"\x74\x00"
    b += bytes.fromhex("c70201000000")                # *count = 1
    b += bytes.fromhex("4d85c9")                      # test r9, r9
    jz2 = len(b); b += b"\x74\x00"
    b += bytes.fromhex("41c70106000000")              # *chars = 6
    b += bytes.fromhex("4d85c0")                      # test r8, r8
    jz3 = len(b); b += b"\x74\x00"
    b += b"\x48\xb8" + struct.pack("<Q", 0x0055002D006E0065)  # "en-U"
    b += bytes.fromhex("498900")                      # mov [r8], rax
    b += bytes.fromhex("41c74008") + struct.pack("<I", 0x53)  # "S" + NUL
    b += bytes.fromhex("b801000000")                  # 返回 1
    b += bytes.fromhex("c3")
    one = len(b)
    b += bytes.fromhex("b801000000")
    b += bytes.fromhex("c3")
    for at in (jz, jz2, jz3):
        b[at + 1] = (one - (at + 2)) & 0xFF
    return bytes(b)


def _uilang_simple_stub() -> bytes:
    return b"\xb8" + struct.pack("<I", LANGID_EN_US) + b"\xc3"


def _hkl_stub() -> bytes:
    return b"\x48\xb8" + struct.pack("<Q", HKL_EN_US) + b"\xc3"


def _langid_stub() -> bytes:
    return b"\xb8" + struct.pack("<I", LANGID_EN_US) + b"\xc3"

MARK8 = b"\x11"


# ---- RegQueryValueExW 桩：伪造设备区域（DeviceRegion） ----

def _modrm_len(code: bytes, i: int) -> int:
    """跳过 ModRM/SIB/disp，返回下一条指令偏移。"""
    modrm = code[i]
    i += 1
    mod, rm = modrm >> 6, modrm & 7
    if mod == 3:
        return i
    if rm == 4:
        sib = code[i]
        i += 1
        if mod == 0 and (sib & 7) == 5:
            i += 4
    elif mod == 0 and rm == 5:
        raise RuntimeError("函数序言含 RIP 相对寻址")
    if mod == 1:
        i += 1
    elif mod == 2:
        i += 4
    return i


def _insn_len(code: bytes, start: int) -> int:
    """估算一条 x64 指令长度，只支持常见序言指令。"""
    i = start
    while i < len(code) and code[i] in (0x66, 0x67, 0xF0, 0xF2, 0xF3,
                                        0x2E, 0x36, 0x3E, 0x26, 0x64, 0x65):
        i += 1
    rex = 0
    if i < len(code) and 0x40 <= code[i] <= 0x4F:
        rex = code[i]
        i += 1
    op = code[i]
    i += 1
    modrm, imm = False, 0
    if op == 0x0F:
        op2 = code[i]
        i += 1
        if 0x80 <= op2 <= 0x8F:
            raise RuntimeError("函数序言含相对跳转")
        modrm = op2 in (0x10, 0x11, 0x1E, 0x1F, 0x28, 0x29, 0x6F,
                        0xAF, 0xB6, 0xB7, 0xBE, 0xBF)
    elif 0x50 <= op <= 0x5F or op in (0x90, 0xC3, 0xCC, 0xF8, 0xF9):
        pass
    elif op == 0x6A:
        imm = 1
    elif op == 0x68:
        imm = 4
    elif 0xB8 <= op <= 0xBF:
        imm = 8 if rex & 8 else 4
    elif op in (0xE8, 0xE9, 0xEB) or 0x70 <= op <= 0x7F:
        raise RuntimeError("函数序言含相对跳转")
    elif op in (0x80, 0x83):
        modrm, imm = True, 1
    elif op == 0x81:
        modrm, imm = True, 4
    elif op in (0x01, 0x03, 0x09, 0x0B, 0x11, 0x21, 0x29, 0x2B, 0x31,
                0x33, 0x39, 0x3B, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89,
                0x8A, 0x8B, 0x8D, 0xD1, 0xD3, 0xF7, 0xFF):
        modrm = True
    else:
        raise RuntimeError(f"函数序言含未知指令 0x{op:02X}")
    if modrm:
        i = _modrm_len(code, i)
    return i - start + imm


def _copy_len(code: bytes, need: int) -> int:
    """计算至少覆盖 need 字节所需的完整指令长度。"""
    n = 0
    while n < need:
        n += _insn_len(code, n)
    return n


def _regq_stub() -> bytes:
    """RegQueryValueExW 桩：值名为 DeviceRegion 时返回美国 GeoID 244。"""
    b = bytearray()
    holes, labels = [], {}

    def jcc(op: int, label: str):
        """写入 6 字节条件跳转，稍后回填。"""
        b.extend((0x0F, op))
        holes.append((len(b), label))
        b.extend(b"\0\0\0\0")

    def mark(name: str):
        labels[name] = len(b)

    # 比较值名 "DeviceRegion"（UTF-16LE）
    b.extend(bytes.fromhex("4885d2"))                 # test rdx, rdx
    jcc(0x84, "tramp")                                # 无值名则走原函数
    for off, word in ((0, 0x0069007600650044),
                      (8, 0x0065005200650063),
                      (16, 0x006E006F00690067)):
        b.extend(bytes.fromhex("488b42") + bytes([off]))   # mov rax, [rdx+off]
        b.extend(b"\x49\xba" + struct.pack("<Q", word))
        b.extend(bytes.fromhex("4c3bd0"))             # cmp rax, r10
        jcc(0x85, "tramp")
    b.extend(bytes.fromhex("66837a1800"))             # cmp word [rdx+24], 0
    jcc(0x85, "tramp")

    # 类型 REG_DWORD
    b.extend(bytes.fromhex("4d85c9"))                 # test r9, r9
    jcc(0x84, "no_type")
    b.extend(bytes.fromhex("41c701") + struct.pack("<I", 4))
    mark("no_type")

    # 数据长度 4 字节
    b.extend(bytes.fromhex("4c8b5c2430"))             # mov r11, [rsp+30h]
    b.extend(bytes.fromhex("4d85db"))                 # test r11, r11
    jcc(0x84, "no_cb")
    b.extend(bytes.fromhex("41c703") + struct.pack("<I", 4))
    mark("no_cb")

    # 数据内容：美国 GeoID
    b.extend(bytes.fromhex("4c8b542428"))             # mov r10, [rsp+28h]
    b.extend(bytes.fromhex("4d85d2"))                 # test r10, r10
    jcc(0x84, "done")
    b.extend(bytes.fromhex("41c702") + struct.pack("<I", 244))
    mark("done")
    b.extend(bytes.fromhex("33c0c3"))                 # xor eax, eax; ret

    # 转发块：跳回 trampoline
    mark("tramp")
    b.extend(b"\x48\xb8" + MARK8 * 8)                 # mov rax, <tramp>
    b.extend(bytes.fromhex("ffe0"))                   # jmp rax
    for pos, label in holes:
        struct.pack_into("<i", b, pos, labels[label] - (pos + 4))
    return bytes(b)


STUB_REGQ_X64 = _regq_stub()


def _make_tramp(addr: int, orig: bytes) -> bytes:
    """复制原函数开头指令，执行后跳回原位且不破坏寄存器。"""
    n = _copy_len(orig, 12)
    if n > 40:
        raise RuntimeError(f"RegQueryValueExW 序言过长（{n} 字节）")
    return (orig[:n]
            + b"\x50"                                        # push rax
            + b"\x48\xb8" + struct.pack("<Q", addr + n)      # mov rax, <原位>
            + b"\x48\x87\x04\x24"                            # xchg rax, [rsp]
            + b"\xc3")                                       # ret


TZ_NAME = "Singapore Standard Time"
BIAS = -480

LOCALE_NAME = "en-US"
LOCALE_LCID = 0x0409

LANGID_EN_US = 0x0409
HKL_EN_US = 0x04090409

OFF_GEO, OFF_GEOID, OFF_TZ_DYN, OFF_TZ_STD = 0x00, 0x40, 0x80, 0xC0
OFF_LOCALE_USER, OFF_LOCALE_SYS = 0x100, 0x140
OFF_LCID_USER, OFF_LCID_SYS = 0x180, 0x1A0
OFF_KBL_LIST, OFF_KBL = 0x1C0, 0x1E0
OFF_UILANG_PREF = 0x200
OFF_UILANG_SYS, OFF_UILANG_THREAD = 0x240, 0x280
OFF_LANGID_USER, OFF_LANGID_SYS = 0x2C0, 0x2D0
OFF_UILANG_SIMPLE, OFF_UILANG_SIMPLE2 = 0x2E0, 0x2F0
OFF_REGQ, OFF_REGQ_TRAMP = 0x300, 0x3C0
OFF_TMPL_DYN, OFF_TMPL_STD = 0x400, 0x600
BLOB_SIZE = 0xA00

ARCH_X64 = 0x8664

GROUP_GEO = "geo"
GROUP_TZ = "tz"
GROUP_LOCALE = "locale"
GROUP_IME = "ime"
GROUP_REG = "reg"

GROUP_LABELS = {
    GROUP_GEO: "地区",
    GROUP_TZ: "时区",
    GROUP_LOCALE: "初始地区",
    GROUP_IME: "输入法",
    GROUP_REG: "设备区域",
}

ALL_GROUPS = (GROUP_GEO, GROUP_TZ, GROUP_LOCALE, GROUP_IME, GROUP_REG)

API_MODULE = {
    "GetKeyboardLayoutList": "user32.dll",
    "GetKeyboardLayout": "user32.dll",
    "RegQueryValueExW": "advapi32.dll",
}

STUBS = (
    (GROUP_GEO, "GetUserDefaultGeoName", OFF_GEO, STUB_GEO_X64),
    (GROUP_GEO, "GetUserGeoID", OFF_GEOID, STUB_GEOID_X64),
    (GROUP_TZ, "GetDynamicTimeZoneInformation", OFF_TZ_DYN,
     _tz_stub(430)),
    (GROUP_TZ, "GetTimeZoneInformation", OFF_TZ_STD,
     _tz_stub(172)),
    (GROUP_LOCALE, "GetUserDefaultLocaleName", OFF_LOCALE_USER, STUB_LOCALE_X64),
    (GROUP_LOCALE, "GetSystemDefaultLocaleName", OFF_LOCALE_SYS, STUB_LOCALE_X64),
    (GROUP_LOCALE, "GetUserDefaultLCID", OFF_LCID_USER, STUB_LCID_X64),
    (GROUP_LOCALE, "GetSystemDefaultLCID", OFF_LCID_SYS, STUB_LCID_X64),
    (GROUP_IME, "GetKeyboardLayoutList", OFF_KBL_LIST, _kbl_list_stub()),
    (GROUP_IME, "GetKeyboardLayout", OFF_KBL, _hkl_stub()),
    (GROUP_IME, "GetUserPreferredUILanguages", OFF_UILANG_PREF, _uilang_stub()),
    (GROUP_IME, "GetSystemPreferredUILanguages", OFF_UILANG_SYS, _uilang_stub()),
    (GROUP_IME, "GetThreadPreferredUILanguages", OFF_UILANG_THREAD, _uilang_stub()),
    (GROUP_IME, "GetUserDefaultUILanguage", OFF_UILANG_SIMPLE, _uilang_simple_stub()),
    (GROUP_IME, "GetSystemDefaultUILanguage", OFF_UILANG_SIMPLE2,
     _uilang_simple_stub()),
    (GROUP_IME, "GetUserDefaultLangID", OFF_LANGID_USER, _langid_stub()),
    (GROUP_IME, "GetSystemDefaultLangID", OFF_LANGID_SYS, _langid_stub()),
    (GROUP_REG, "RegQueryValueExW", OFF_REGQ, STUB_REGQ_X64),
)


def stubs_for(groups=None) -> list:
    if groups is None:
        return list(STUBS)
    groups = set(groups)
    return [s for s in STUBS if s[0] in groups]


def api_names(groups=None) -> list:
    return [s[1] for s in stubs_for(groups)]

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.GetModuleHandleW.restype = wt.HMODULE
k32.GetModuleHandleW.argtypes = [wt.LPCWSTR]
k32.LoadLibraryW.restype = wt.HMODULE
k32.LoadLibraryW.argtypes = [wt.LPCWSTR]
k32.GetProcAddress.restype = ctypes.c_void_p
k32.GetProcAddress.argtypes = [wt.HMODULE, ctypes.c_char_p]
k32.GetCurrentProcess.restype = wt.HANDLE
k32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                  ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k32.WriteProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                   ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k32.VirtualAllocEx.restype = ctypes.c_void_p
k32.VirtualAllocEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_size_t, wt.DWORD, wt.DWORD]
k32.VirtualProtectEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_size_t, wt.DWORD,
                                 ctypes.POINTER(wt.DWORD)]
k32.FlushInstructionCache.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_size_t]
k32.CreateProcessW.argtypes = [wt.LPCWSTR, wt.LPWSTR, ctypes.c_void_p, ctypes.c_void_p,
                               wt.BOOL, wt.DWORD, ctypes.c_void_p, wt.LPCWSTR,
                               ctypes.c_void_p, ctypes.c_void_p]
k32.ResumeThread.argtypes = [wt.HANDLE]
k32.SuspendThread.argtypes = [wt.HANDLE]
k32.TerminateProcess.argtypes = [wt.HANDLE, wt.UINT]
k32.CloseHandle.argtypes = [wt.HANDLE]
k32.WaitForSingleObject.argtypes = [wt.HANDLE, wt.DWORD]
k32.GetExitCodeProcess.argtypes = [wt.HANDLE, ctypes.POINTER(wt.DWORD)]
k32.CreateToolhelp32Snapshot.restype = wt.HANDLE
k32.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
k32.CreateRemoteThread.restype = wt.HANDLE
k32.CreateRemoteThread.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_size_t,
                                   ctypes.c_void_p, ctypes.c_void_p, wt.DWORD,
                                   ctypes.POINTER(wt.DWORD)]
k32.GetExitCodeThread.argtypes = [wt.HANDLE, ctypes.POINTER(wt.DWORD)]


class STARTUPINFO(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD), ("lpReserved", wt.LPWSTR), ("lpDesktop", wt.LPWSTR),
                ("lpTitle", wt.LPWSTR), ("dwX", wt.DWORD), ("dwY", wt.DWORD),
                ("dwXSize", wt.DWORD), ("dwYSize", wt.DWORD), ("dwXCountChars", wt.DWORD),
                ("dwYCountChars", wt.DWORD), ("dwFillAttribute", wt.DWORD),
                ("dwFlags", wt.DWORD), ("wShowWindow", wt.WORD), ("cbReserved2", wt.WORD),
                ("lpReserved2", ctypes.c_void_p), ("hStdInput", wt.HANDLE),
                ("hStdOutput", wt.HANDLE), ("hStdError", wt.HANDLE)]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [("hProcess", wt.HANDLE), ("hThread", wt.HANDLE),
                ("dwProcessId", wt.DWORD), ("dwThreadId", wt.DWORD)]


class MODULEENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("th32ModuleID", wt.DWORD),
                ("th32ProcessID", wt.DWORD), ("GlblcntUsage", wt.DWORD),
                ("ProccntUsage", wt.DWORD), ("modBaseAddr", ctypes.c_void_p),
                ("modBaseSize", wt.DWORD), ("hModule", wt.HMODULE),
                ("szModule", wt.WCHAR * 256), ("szExePath", wt.WCHAR * 260)]

CREATE_SUSPENDED, CREATE_NEW_PROCESS_GROUP, CREATE_UNICODE_ENVIRONMENT = 0x4, 0x200, 0x400
MEM_COMMIT_RESERVE, PAGE_EXECUTE_READWRITE, PAGE_READWRITE = 0x3000, 0x40, 0x04


def _err(what: str) -> OSError:
    return OSError(f"{what} 失败，GetLastError={ctypes.get_last_error()}")


def read_mem(h, addr: int, size: int) -> bytes:
    buf = ctypes.create_string_buffer(size)
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, size, ctypes.byref(got)):
        raise _err(f"读取 0x{addr:X}")
    return buf.raw[:got.value]


def read_str(h, addr: int, maxlen: int) -> str:
    """读取目标进程里以 NUL 结尾的 ASCII 字符串。"""
    return read_mem(h, addr, maxlen).split(b"\0", 1)[0].decode("ascii", "replace")


def write_mem(h, addr: int, data: bytes):
    old = wt.DWORD()
    if not k32.VirtualProtectEx(h, ctypes.c_void_p(addr), len(data),
                                PAGE_EXECUTE_READWRITE, ctypes.byref(old)):
        raise _err(f"改保护 0x{addr:X}")
    written = ctypes.c_size_t()
    ok = k32.WriteProcessMemory(h, ctypes.c_void_p(addr), data, len(data), ctypes.byref(written))
    k32.VirtualProtectEx(h, ctypes.c_void_p(addr), len(data), old, ctypes.byref(old))
    if not ok or written.value != len(data):
        raise _err(f"写入 0x{addr:X}")
    k32.FlushInstructionCache(h, ctypes.c_void_p(addr), len(data))


def resolve_local(name: str) -> int:
    addr = k32.GetProcAddress(k32.GetModuleHandleW("kernel32.dll"), name.encode())
    if not addr:
        raise RuntimeError(f"kernel32 里找不到 {name}")
    return addr


def remote_modules(pid: int) -> dict:
    snap = k32.CreateToolhelp32Snapshot(0x8 | 0x10, pid)
    if not snap or snap == ctypes.c_void_p(-1).value:
        raise _err("CreateToolhelp32Snapshot")
    mods = {}
    try:
        me = MODULEENTRY32W()
        me.dwSize = ctypes.sizeof(me)
        ok = k32.Module32FirstW(snap, ctypes.byref(me))
        while ok:
            key, base = me.szModule.lower(), me.modBaseAddr
            if base and (key not in mods or base < mods[key]):
                mods[key] = base
            ok = k32.Module32NextW(snap, ctypes.byref(me))
    finally:
        k32.CloseHandle(snap)
    if not mods:
        raise RuntimeError("拿不到目标进程的模块列表")
    return mods


def ensure_modules(h: int, pid: int, dlls) -> dict:
    mods = remote_modules(pid)
    missing = [d for d in dlls if d.lower() not in mods]
    if not missing:
        return mods

    addr = remote_export(h, mods["kernel32.dll"], "LoadLibraryW", mods)
    for dll in missing:
        saddr = _remote_str(h, dll)
        stub = (b"\x48\xb8" + struct.pack("<Q", addr)
                + b"\x48\xb9" + struct.pack("<Q", saddr)
                + b"\xff\xd0"
                + b"\xc3")
        run_remote(h, pid, stub)
    time.sleep(0.2)
    return remote_modules(pid)

_REMOTE_STRS = {}


def _remote_str(h: int, s: str) -> int:
    key = s
    if key in _REMOTE_STRS:
        return _REMOTE_STRS[key]
    buf = ctypes.create_unicode_buffer(s)
    size = len(buf)
    addr = k32.VirtualAllocEx(h, None, size, MEM_COMMIT_RESERVE, PAGE_READWRITE)
    if not addr:
        raise _err("VirtualAllocEx")
    k32.WriteProcessMemory(h, ctypes.c_void_p(addr), buf, size,
                           ctypes.byref(ctypes.c_size_t()))
    _REMOTE_STRS[key] = addr
    return addr


def run_remote(h: int, pid: int, code: bytes) -> int:
    addr = k32.VirtualAllocEx(h, None, max(len(code), 0x1000),
                              MEM_COMMIT_RESERVE, PAGE_EXECUTE_READWRITE)
    if not addr:
        raise _err("VirtualAllocEx")
    k32.WriteProcessMemory(h, ctypes.c_void_p(addr), code, len(code),
                           ctypes.byref(ctypes.c_size_t()))
    tid = ctypes.c_ulong()
    th = k32.CreateRemoteThread(h, None, 0, ctypes.c_void_p(addr),
                                 None, 0, ctypes.byref(tid))
    if not th:
        raise _err("CreateRemoteThread")
    k32.WaitForSingleObject(th, 0xFFFFFFFF)
    code_out = wt.DWORD()
    k32.GetExitCodeThread(th, ctypes.byref(code_out))
    k32.CloseHandle(th)
    return code_out.value


def process_arch(pid: int) -> int:
    try:
        mods = remote_modules(pid)
    except Exception:
        return ARCH_X64
    if any(b and b < 0x100000000 for b in mods.values()):
        return ARCH_X86_LEGACY
    return ARCH_X64

ARCH_X86_LEGACY = 0x14C


def remote_export(h, mod_base: int, func: str, mods: dict, depth: int = 0) -> int:
    if depth > 4:
        raise RuntimeError(f"{func} 转发层数过多")
    dos = read_mem(h, mod_base, 0x40)
    pe = struct.unpack_from("<I", dos, 0x3C)[0]
    opt = read_mem(h, mod_base + pe + 24, 0x110)
    magic = struct.unpack_from("<H", opt, 0)[0]
    dd = 96 if magic == 0x10B else 112
    exp_rva, exp_size = struct.unpack_from("<II", opt, dd)
    if not exp_rva:
        raise RuntimeError("模块没有导出表")
    ed = read_mem(h, mod_base + exp_rva, 40)
    n_names = struct.unpack_from("<I", ed, 24)[0]
    funcs_rva, names_rva, ords_rva = struct.unpack_from("<III", ed, 28)

    for i in range(n_names):
        name_rva = struct.unpack_from("<I", read_mem(h, mod_base + names_rva + i * 4, 4))[0]
        if read_str(h, mod_base + name_rva, 48) != func:
            continue
        ordinal = struct.unpack_from("<H", read_mem(h, mod_base + ords_rva + i * 2, 2))[0]
        f_rva = struct.unpack_from("<I", read_mem(h, mod_base + funcs_rva + ordinal * 4, 4))[0]
        if exp_rva <= f_rva < exp_rva + exp_size:
            mod, _, fn = read_str(h, mod_base + f_rva, 64).partition(".")
            base = mods.get((mod + ".dll").lower())
            if not base:
                raise RuntimeError(f"转发的模块 {mod} 不在进程里")
            return remote_export(h, base, fn, mods, depth + 1)
        return mod_base + f_rva
    raise RuntimeError(f"模块里找不到导出 {func}")


def resolve_thunk(h, addr: int) -> int:
    """跳过 jmp [rip+disp] 跳板，返回真实函数入口。"""
    head = read_mem(h, addr, 16)
    if head[:3] == b"\x48\xff\x25":
        disp = struct.unpack_from("<i", head, 3)[0]
        ptr = read_mem(h, addr + 7 + disp, 8)
        target = struct.unpack("<Q", ptr)[0]
        if target:
            return target
    return addr


def target_addresses(h, pid: int, names) -> dict:
    dlls = {API_MODULE.get(n, "kernel32.dll") for n in names}
    try:
        mods = ensure_modules(h, pid, dlls)
    except Exception:
        # 快照不可用时退回本进程地址，同一次开机系统 DLL 基址一致
        mods = {}
    addrs = {}
    for name in names:
        dll = API_MODULE.get(name, "kernel32.dll")
        base = mods.get(dll)
        if base:
            try:
                addrs[name] = resolve_thunk(h, remote_export(h, base, name, mods))
                continue
            except Exception:
                pass
        local_dll = k32.GetModuleHandleW(dll) or k32.LoadLibraryW(dll)
        if not local_dll:
            raise RuntimeError(f"目标进程里没有 {dll}")
        addr = k32.GetProcAddress(local_dll, name.encode())
        if not addr:
            raise RuntimeError(f"{dll} 里找不到 {name}")
        addrs[name] = resolve_thunk(k32.GetCurrentProcess(), addr)
    return addrs


def patch_bytes(stub_addr: int) -> bytes:
    return b"\x48\xb8" + struct.pack("<Q", stub_addr) + b"\xff\xe0"


def tz_templates() -> tuple[bytes, bytes]:
    enc = TZ_NAME.encode("utf-16-le")
    name32 = enc.ljust(64, b"\0")[:64]

    def _systime():
        return struct.pack("<HHHHHHHH", 0, 0, 0, 0, 0, 0, 0, 0)

    std = (struct.pack("<i", BIAS)
           + name32
           + _systime()
           + struct.pack("<i", 0)
           + name32
           + _systime()
           + struct.pack("<i", 0))
    assert len(std) == 172, len(std)

    dyn = (std
           + b"\x00\x00"
           + enc.ljust(256, b"\0")[:256])
    assert len(dyn) == 430, len(dyn)
    return dyn, std


def build_blob(base: int, groups=None) -> bytes:
    dyn_tmpl, std_tmpl = tz_templates()
    blob = bytearray(BLOB_SIZE)
    end = 0
    for _grp, name, off, stub in sorted(stubs_for(groups), key=lambda s: s[2]):
        if off < end:
            raise RuntimeError(f"桩布局重叠：{name} (0x{off:X} < 0x{end:X})")
        end = off + len(stub)
        if name == "GetDynamicTimeZoneInformation":
            stub = stub.replace(MARK8 * 8, struct.pack("<Q", base + OFF_TMPL_DYN))
        elif name == "GetTimeZoneInformation":
            stub = stub.replace(MARK8 * 8, struct.pack("<Q", base + OFF_TMPL_STD))
        elif name == "RegQueryValueExW":
            stub = stub.replace(MARK8 * 8, struct.pack("<Q", base + OFF_REGQ_TRAMP))
        blob[off:off + len(stub)] = stub
    blob[OFF_TMPL_DYN:OFF_TMPL_DYN + len(dyn_tmpl)] = dyn_tmpl
    blob[OFF_TMPL_STD:OFF_TMPL_STD + len(std_tmpl)] = std_tmpl
    return bytes(blob)


def alloc_stub_page(h) -> int:
    base = k32.VirtualAllocEx(h, None, BLOB_SIZE, MEM_COMMIT_RESERVE, PAGE_EXECUTE_READWRITE)
    if not base:
        raise _err("VirtualAllocEx")
    return base


def wait_addressable(h, addrs, timeout: float = 5.0) -> list:
    deadline = time.time() + timeout
    pending = list(addrs)
    while pending and time.time() < deadline:
        still = []
        for addr in pending:
            old = wt.DWORD()
            if k32.VirtualProtectEx(h, ctypes.c_void_p(addr), 12,
                                    PAGE_EXECUTE_READWRITE, ctypes.byref(old)):
                k32.VirtualProtectEx(h, ctypes.c_void_p(addr), 12, old, ctypes.byref(old))
            else:
                still.append(addr)
        pending = still
        if pending:
            time.sleep(0.003)
    return pending


def install(h, hthread, pid: int, groups=None):
    stubs = stubs_for(groups)
    names = [s[1] for s in stubs]
    addrs, last = None, None
    deadline = time.time() + 5.0
    while time.time() < deadline and addrs is None:
        try:
            addrs = target_addresses(h, pid, names)
        except Exception as exc:
            last = exc
            time.sleep(0.005)
    if addrs is None:
        raise RuntimeError(f"解析函数地址失败：{last}")

    stuck = wait_addressable(h, [addrs[n] for n in names])
    if stuck:
        raise RuntimeError(
            "目标进程内存一直不可写（" +
            ", ".join(f"0x{a:X}" for a in stuck) +
            "），可能被安全软件拦了")

    if hthread:
        k32.SuspendThread(hthread)
    try:
        base = alloc_stub_page(h)
        if os.environ.get("LAUNCHER_UNLOCK_DEBUG") == "1":
            print(f"  桩页 @0x{base:X}")
        blob = build_blob(base, groups)
        written = ctypes.c_size_t()
        if not k32.WriteProcessMemory(h, ctypes.c_void_p(base), blob, len(blob),
                                      ctypes.byref(written)):
            raise _err("写入桩代码")
        # 设备区域桩需要跳回原函数，按真实序言生成 trampoline
        if GROUP_REG in set(groups or ALL_GROUPS):
            addr = addrs["RegQueryValueExW"]
            tramp = _make_tramp(addr, read_mem(h, addr, 32))
            write_mem(h, base + OFF_REGQ_TRAMP, tramp)
        debug = os.environ.get("LAUNCHER_UNLOCK_DEBUG") == "1"
        for _grp, name, off, _stub in stubs:
            if debug:
                print(f"  {name} @0x{addrs[name]:X} 原字节 {read_mem(h, addrs[name], 16).hex(' ')}")
            write_mem(h, addrs[name], patch_bytes(base + off))
    finally:
        if hthread:
            k32.ResumeThread(hthread)
    return base, addrs


def verify(h, base: int, addrs: dict, groups=None) -> list:
    stubs = stubs_for(groups)
    valid = {off for _g, _n, off, _s in stubs}
    bad = []
    for _g, name, _off, _s in stubs:
        try:
            head = read_mem(h, addrs[name], 12)
        except OSError:
            bad.append(name)
            continue
        if not (head[:2] == b"\x48\xb8"
                and struct.unpack_from("<Q", head, 2)[0] - base in valid):
            bad.append(name)
    if GROUP_TZ in (groups or ALL_GROUPS):
        try:
            key = read_mem(h, base + OFF_TMPL_DYN + 174, 64).decode("utf-16-le", "replace")
            if TZ_NAME not in key:
                bad.extend(("GetDynamicTimeZoneInformation", "GetTimeZoneInformation"))
        except OSError:
            bad.extend(("GetDynamicTimeZoneInformation", "GetTimeZoneInformation"))
    return bad


def pe_machine(path: str):
    with open(path, "rb") as f:
        head = f.read(0x40)
        if head[:2] != b"MZ":
            return None
        f.seek(struct.unpack_from("<I", head, 0x3C)[0])
        sig = f.read(6)
        if sig[:4] != b"PE\0\0":
            return None
        return struct.unpack_from("<H", sig, 4)[0]


def app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def find_target(explicit, here=None):
    if explicit:
        if not os.path.isfile(explicit):
            raise RuntimeError(f"找不到文件：{explicit}")
        return os.path.abspath(explicit)
    here = here or app_dir()
    for name in ("Plain Craft Launcher Community Edition.exe", "PCL.exe", "PCL-CE.exe"):
        p = os.path.join(here, name)
        if os.path.isfile(p):
            return p
    try:
        me = os.path.basename(sys.executable).lower()
        hits = [f for f in os.listdir(here)
                if f.lower().endswith(".exe") and f.lower() != me
                and ("pcl" in f.lower() or f.lower().startswith("plain craft launcher"))]
        if hits:
            return os.path.join(here, sorted(hits)[0])
    except OSError:
        pass
    raise RuntimeError("没在当前目录找到启动器，请手动选择 exe")


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def skip_elevate() -> bool:
    return os.environ.get("LAUNCHER_UNLOCK_NO_ELEVATE") == "1"


def relaunch_as_admin() -> bool:
    if getattr(sys, "frozen", False):
        exe, params = sys.executable, subprocess.list2cmdline(sys.argv[1:])
    else:
        exe = sys.executable
        params = subprocess.list2cmdline([os.path.abspath(sys.argv[0])] + sys.argv[1:])
    try:
        r = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, os.getcwd(), 1)
    except Exception:
        return False
    return r > 32


def dump_trace(exc: Exception):
    import traceback
    path = os.path.join(os.environ.get("TEMP", "."), "LauncherRegionUnlock.log")
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(time.strftime("\n===== %Y-%m-%d %H:%M:%S =====\n"))
            f.write(traceback.format_exc())
    except OSError:
        pass
    return path


def group_summary(groups) -> str:
    groups = set(groups or ALL_GROUPS)
    parts = []
    if GROUP_GEO in groups:
        parts.append("地区=US")
    if GROUP_TZ in groups:
        parts.append(f"时区={TZ_NAME}")
    if GROUP_LOCALE in groups:
        parts.append(f"初始地区={LOCALE_NAME}")
    if GROUP_IME in groups:
        parts.append(f"输入法=en-US(0x{HKL_EN_US:08X})")
    if GROUP_REG in groups:
        parts.append("设备区域=美国(244)")
    return "，".join(parts) if parts else "（未启用任何伪装）"


def run(exe: str, extra=(), wait: bool = False, log=print, groups=None) -> int:
    groups = tuple(groups or ALL_GROUPS)
    machine = pe_machine(exe)
    if machine is None:
        raise RuntimeError(f"{exe} 不是 PE 文件")
    if machine != ARCH_X64:
        raise RuntimeError(f"{os.path.basename(exe)} 是 32 位程序（0x{machine:04X}），"
                           "本工具只支持 64 位版本")
    log(f"目标：{os.path.basename(exe)}（x64）")
    log(f"伪装：{group_summary(groups)}")

    cmdline = ctypes.create_unicode_buffer(subprocess.list2cmdline([exe] + list(extra)))
    si, pi = STARTUPINFO(), PROCESS_INFORMATION()
    si.cb = ctypes.sizeof(si)
    flags = CREATE_SUSPENDED | CREATE_NEW_PROCESS_GROUP | CREATE_UNICODE_ENVIRONMENT
    if not k32.CreateProcessW(exe, cmdline, None, None, False, flags, None,
                              os.path.dirname(exe), ctypes.byref(si), ctypes.byref(pi)):
        err = ctypes.get_last_error()
        if err == 740:
            raise RuntimeError("启动器要求管理员权限，本工具需要以管理员身份运行")
        raise RuntimeError(f"启动失败，GetLastError={err}")
    log(f"已挂起启动，PID {pi.dwProcessId}")

    try:
        if k32.ResumeThread(pi.hThread) == 0xFFFFFFFF:
            raise RuntimeError("ResumeThread 失败")
        if os.environ.get("LAUNCHER_UNLOCK_NO_PATCH") == "1":
            log("调试模式：跳过打桩")
            base, addrs = 0, {}
        else:
            base, addrs = install(pi.hProcess, pi.hThread, pi.dwProcessId, groups)
            log(f"已注入 {len(addrs)} 个桩")
    except Exception as exc:
        k32.TerminateProcess(pi.hProcess, 1)
        k32.CloseHandle(pi.hThread)
        k32.CloseHandle(pi.hProcess)
        raise RuntimeError(str(exc)) from exc

    bad = verify(pi.hProcess, base, addrs, groups) if addrs else []
    k32.CloseHandle(pi.hThread)
    if bad:
        log(f"校验失败：{', '.join(bad)} 没生效，功能可能仍被限制")
    elif addrs:
        log(f"校验通过：{group_summary(groups)}")

    if wait:
        k32.WaitForSingleObject(pi.hProcess, 0xFFFFFFFF)
        code = wt.DWORD()
        k32.GetExitCodeProcess(pi.hProcess, ctypes.byref(code))
        k32.CloseHandle(pi.hProcess)
        log(f"启动器退出码 {code.value}")
        return code.value
    k32.CloseHandle(pi.hProcess)
    return 0


def current_signals() -> dict:
    out = {}
    try:
        buf = ctypes.create_unicode_buffer(16)
        n = k32.GetUserDefaultGeoName(buf, 16)
        out["geo"] = buf.value if n > 1 else "?"
    except Exception:
        out["geo"] = "?"
    try:
        out["tz"] = time.tzname[0] if time.tzname else "?"
    except Exception:
        out["tz"] = "?"
    try:
        buf = ctypes.create_unicode_buffer(16)
        n = k32.GetUserDefaultLocaleName(buf, 16)
        out["locale"] = buf.value if n > 1 else "?"
    except Exception:
        out["locale"] = "?"
    try:
        u32 = ctypes.WinDLL("user32", use_last_error=True)
        u32.GetKeyboardLayoutList.argtypes = [ctypes.c_int, ctypes.c_void_p]
        n = u32.GetKeyboardLayoutList(0, None)
        if n > 0:
            buf = (ctypes.c_void_p * n)()
            u32.GetKeyboardLayoutList(n, ctypes.byref(buf))
            out["kbl"] = f"0x{ctypes.cast(buf[0], ctypes.c_void_p).value:08X}"
        else:
            out["kbl"] = "?"
    except Exception:
        out["kbl"] = "?"
    try:
        import winreg
        with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Control Panel\DeviceRegion",
                0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as k:
            out["device"] = str(winreg.QueryValueEx(k, "DeviceRegion")[0])
    except OSError:
        out["device"] = "?"
    return out


def die(msg: str, code: int = 1):
    print(f"[!] {msg}", file=sys.stderr)
    if sys.stdout is None:
        ctypes.windll.user32.MessageBoxW(None, msg, "启动器区域限制解除器", 0x10)
    raise SystemExit(code)


def main() -> int:
    ap = argparse.ArgumentParser(description="启动器区域限制解除器（仅 x64）")
    ap.add_argument("exe", nargs="?", help="启动器的 exe 路径，省略则在当前目录找")
    ap.add_argument("--dry-run", action="store_true", help="只检查不改进程")
    ap.add_argument("--wait", action="store_true", help="等启动器退出并打印退出码")
    ap.add_argument("--no-geo", action="store_true", help="不伪装地区")
    ap.add_argument("--no-tz", action="store_true", help="不伪装时区")
    ap.add_argument("--no-locale", action="store_true", help="不伪装初始地区")
    ap.add_argument("--no-ime", action="store_true", help="不伪装输入法")
    ap.add_argument("--no-reg", action="store_true", help="不伪装设备区域")
    ap.add_argument("--only-ime", action="store_true",
                    help="只伪装输入法（其余全关）")
    ns, rest = ap.parse_known_args()

    if ns.only_ime:
        groups = [GROUP_IME]
    else:
        groups = [g for g in ALL_GROUPS
                  if not (g == GROUP_GEO and ns.no_geo)
                  and not (g == GROUP_TZ and ns.no_tz)
                  and not (g == GROUP_LOCALE and ns.no_locale)
                  and not (g == GROUP_IME and ns.no_ime)
                  and not (g == GROUP_REG and ns.no_reg)]
    if not groups:
        die("至少要开启一项伪装")

    if not is_admin() and not skip_elevate():
        print("启动器要求管理员权限，正在提权重启…")
        if relaunch_as_admin():
            return 0
        die("提权被拒绝，请右键以管理员身份运行")

    try:
        exe = find_target(ns.exe)
        if ns.dry_run:
            print(f"目标：{exe}")
            print(f"架构：0x{pe_machine(exe):04X}")
            print(f"伪装：{group_summary(groups)}")
            print("STCaoMei")
            return 0
        code = run(exe, [a for a in rest if a != "--"], ns.wait, groups=groups)
        print("STCaoMei")
        return code
    except RuntimeError as exc:
        dump_trace(exc)
        die(str(exc))
    return 1

if __name__ == "__main__":
    sys.exit(main())
