; 注入到启动器进程里的 x64 桩代码（只用于生成字节，运行时不需要 .obj）
; 编译：ml64 /c /Fo stubs.obj stubs.asm
OPTION CASEMAP:NONE

.code

; int GetUserDefaultGeoName(LPWSTR buf, int cch)  ->  "US\0", 返回 3
PUBLIC stub_geo
stub_geo PROC
    test    rcx, rcx
    jz      short geo_done
    cmp     edx, 3
    jl      short geo_done
    mov     dword ptr [rcx], 530055h        ; "US"（UTF-16LE: 55 00 53 00）
    mov     word ptr [rcx+4], 0
geo_done:
    mov     eax, 3
    ret
stub_geo ENDP

; GEOID GetUserGeoID(GEOCLASS) -> 244 (United States)
PUBLIC stub_geoid
stub_geoid PROC
    mov     eax, 244
    ret
stub_geoid ENDP

; BOOL GetDynamicTimeZoneInformation(PDTZI)  rcx = out
; 2 处 11h 占位符由 Python 填成模板地址
PUBLIC stub_dyntz
stub_dyntz PROC
    test    rcx, rcx
    jz      short dyn_fail
    push    rdi
    push    rsi
    mov     rdi, rcx
    mov     rsi, 1111111111111111h
    mov     ecx, 91                         ; 91*4 = 364 字节
    rep movsd
    pop     rsi
    pop     rdi
    mov     eax, 1
    ret
dyn_fail:
    xor     eax, eax
    ret
stub_dyntz ENDP

; DWORD GetTimeZoneInformation(LPTZI)  rcx = out
PUBLIC stub_tz
stub_tz PROC
    test    rcx, rcx
    jz      short tz_fail
    push    rdi
    push    rsi
    mov     rdi, rcx
    mov     rsi, 2222222222222222h
    mov     ecx, 27                         ; 27*4 = 108 字节
    rep movsd
    pop     rsi
    pop     rdi
    mov     eax, 1                          ; TIME_ZONE_ID_STANDARD
    ret
tz_fail:
    xor     eax, eax
    ret
stub_tz ENDP

END
