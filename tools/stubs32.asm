; 32 位（WOW64）桩代码，32 位启动器用
; 编译：ml -c -Fo stubs32.obj stubs32.asm
.386
.model flat

.code

; int GetUserDefaultGeoName(LPWSTR buf, int cch)  stdcall
PUBLIC stub_geo32
stub_geo32 PROC
    mov     ecx, [esp+4]
    test    ecx, ecx
    jz      short geo32_done
    cmp     dword ptr [esp+8], 3
    jl      short geo32_done
    mov     dword ptr [ecx], 530055h        ; "US"
    mov     word ptr [ecx+4], 0
geo32_done:
    mov     eax, 3
    ret     8
stub_geo32 ENDP

; GEOID GetUserGeoID(GEOCLASS) -> 244
PUBLIC stub_geoid32
stub_geoid32 PROC
    mov     eax, 244
    ret     4
stub_geoid32 ENDP

; BOOL GetDynamicTimeZoneInformation(PDTZI)
PUBLIC stub_dyntz32
stub_dyntz32 PROC
    mov     ecx, [esp+4]
    test    ecx, ecx
    jz      short dyn32_fail
    push    edi
    push    esi
    mov     edi, ecx
    mov     esi, 11111111h
    mov     ecx, 91
    rep movsd
    pop     esi
    pop     edi
    mov     eax, 1
    ret     4
dyn32_fail:
    xor     eax, eax
    ret     4
stub_dyntz32 ENDP

; DWORD GetTimeZoneInformation(LPTZI)
PUBLIC stub_tz32
stub_tz32 PROC
    mov     ecx, [esp+4]
    test    ecx, ecx
    jz      short tz32_fail
    push    edi
    push    esi
    mov     edi, ecx
    mov     esi, 22222222h
    mov     ecx, 27
    rep movsd
    pop     esi
    pop     edi
    mov     eax, 1
    ret     4
tz32_fail:
    xor     eax, eax
    ret     4
stub_tz32 ENDP

END
