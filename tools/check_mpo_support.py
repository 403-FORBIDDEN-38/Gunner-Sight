"""
Real Overlay PoC：检测 MPO 支持（修正版）
用 ctypes 手动调 vtable，IID 用 c_ubyte 数组避免 c_char_p 截断。
"""
import ctypes
import ctypes.wintypes as wt

def guid(b):
    return (ctypes.c_ubyte * 16)(*b)

IID_IDXGIFactory1 = guid(b"\x78\xae\x0a\x77\x6f\xf2\xba\x4d\xa8\x29\x25\x3c\x83\xd1\xb3\x87")
IID_IDXGIAdapter1 = guid(b"\x61\x8f\x03\x29\x39\x38\x26\x46\x91\xfd\x08\x68\x79\x01\x1a\x05")
IID_IDXGIOutput2 = guid(b"\xd1\x39\x5e\x59\x24\x27\x63\x46\x99\xb1\x3d\xa4\x44\x17\x58\xc6")

# vtable indices (correct this time)
# IUnknown(3) + IDXGIObject(4) + IDXGIFactory(5) = 12, EnumAdapters1 at 12
IDXGIFactory1_EnumAdapters1 = 12
# IUnknown(3) + IDXGIObject(4) = 7, EnumOutputs at 7
IDXGIAdapter_EnumOutputs = 7
# +3 (GetDesc, CheckInterfaceSupport, GetDesc1) = 10
IDXGIAdapter1_GetDesc1 = 10
# IUnknown(3)+IDXGIObject(4)+IDXGIDeviceSubObject(1)+IDXGIOutput(12)+IDXGIOutput1(4) = 24
IDXGIOutput2_SupportsOverlays = 24

class DXGI_ADAPTER_DESC1(ctypes.Structure):
    _fields_ = [
        ("Description", ctypes.c_wchar * 128),
        ("VendorId", ctypes.c_uint),
        ("DeviceId", ctypes.c_uint),
        ("SubSysId", ctypes.c_uint),
        ("Revision", ctypes.c_uint),
        ("DedicatedVideoMemory", ctypes.c_size_t),
        ("DedicatedSystemMemory", ctypes.c_size_t),
        ("SharedSystemMemory", ctypes.c_size_t),
        ("AdapterLuid", ctypes.c_ulonglong),
        ("Flags", ctypes.c_uint),
    ]

def get_vfunc(this, idx, restype, *argtypes):
    # COM object layout: [0] = vtable pointer, then vtable[idx] = function pointer
    obj = ctypes.cast(this, ctypes.POINTER(ctypes.c_void_p))
    vtbl_ptr = obj[0]
    vtbl = ctypes.cast(vtbl_ptr, ctypes.POINTER(ctypes.c_void_p))
    ptr = vtbl[idx]
    return ctypes.cast(ptr, ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes))

def release(com_ptr):
    if com_ptr:
        f = get_vfunc(com_ptr, 2, ctypes.c_ulong)
        f(com_ptr)

def check_mpo():
    print("=" * 60)
    print("MPO Support Check")
    print("=" * 60)

    dxgi = ctypes.windll.dxgi
    factory = ctypes.c_void_p()
    hr = dxgi.CreateDXGIFactory1(ctypes.byref(IID_IDXGIFactory1), ctypes.byref(factory))
    if hr != 0:
        print(f"[FAIL] CreateDXGIFactory1: 0x{hr:08X}")
        return False
    print("[OK] DXGI Factory created")

    any_mpo = False
    ai = 0
    while True:
        adapter = ctypes.c_void_p()
        f = get_vfunc(factory, IDXGIFactory1_EnumAdapters1, ctypes.c_long,
                      ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p))
        hr = f(factory, ai, ctypes.byref(adapter))
        if hr != 0:
            break

        desc = DXGI_ADAPTER_DESC1()
        f = get_vfunc(adapter, IDXGIAdapter1_GetDesc1, ctypes.c_long,
                      ctypes.POINTER(DXGI_ADAPTER_DESC1))
        f(adapter, ctypes.byref(desc))
        print(f"\n[Adapter {ai}] {desc.Description}")
        print(f"  VRAM: {desc.DedicatedVideoMemory/1024**3:.1f} GB")

        oi = 0
        while True:
            output = ctypes.c_void_p()
            f = get_vfunc(adapter, IDXGIAdapter_EnumOutputs, ctypes.c_long,
                          ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p))
            hr = f(adapter, oi, ctypes.byref(output))
            if hr != 0:
                break

            # QI for IDXGIOutput2 (has SupportsOverlays)
            out2 = ctypes.c_void_p()
            qi = get_vfunc(output, 0, ctypes.c_long,
                           ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
            hr = qi(output, ctypes.byref(IID_IDXGIOutput2), ctypes.byref(out2))
            if hr == 0 and out2:
                sup = get_vfunc(out2, IDXGIOutput2_SupportsOverlays, wt.BOOL)
                try:
                    result = sup(out2)
                    ok = bool(result)
                    print(f"  [Output {oi}] MPO: {'YES' if ok else 'no'}")
                    if ok:
                        any_mpo = True
                except Exception as e:
                    print(f"  [Output {oi}] MPO call error: {e}")
                release(out2)
            else:
                print(f"  [Output {oi}] IDXGIOutput2 unavailable (0x{hr:08X})")
            release(output)
            oi += 1

        release(adapter)
        ai += 1

    release(factory)
    print("\n" + "=" * 60)
    print(f"[RESULT] MPO: {'SUPPORTED' if any_mpo else 'NOT SUPPORTED'}")
    print("=" * 60)
    return any_mpo

if __name__ == "__main__":
    check_mpo()
