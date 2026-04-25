# Plan: Tăng tốc QR Detection

## Context
Hiện tại mỗi ảnh cần ~683+ lần gọi `zxingcpp.read_barcodes()` tuần tự, kèm theo nhiều thao tác dư thừa (GaussianBlur, adaptiveThreshold tính lại nhiều lần trên cùng ảnh, variant trùng lặp, CLAHE tạo mới mỗi lần). Mục tiêu: giảm thời gian xử lý mỗi ảnh mà không giảm accuracy (vẫn giữ 37.5%).

---

## Bottleneck Summary (từ phân tích code)

| Vấn đề | Tác động |
|--------|----------|
| ~683+ `zxingcpp.read_barcodes()` gọi tuần tự | Bottleneck lớn nhất |
| `resize_3x_enhanced` trùng y hệt `resize_3x` | 1 lần decode thừa / crop |
| `cv2.createCLAHE()` tạo lại mỗi crop | CPU waste không cần thiết |
| `GaussianBlur + adaptiveThreshold` tính 3-4 lần trên cùng input | Redundant compute |
| `bilateralFilter(d=9)` chậm O(d²/pixel), ít khi win | Tốn time trên mọi crop |
| Variant order: winner (`resize_3x`, `resize_4x`) nằm giữa list | Early exit không kick in sớm |
| Grid scan 9 cells luôn chạy dù đã có QR-focused region | Thừa khi QR đã locate được |

---

## Chiến lược Tối Ưu (3 Tier)

### Tier 1 - Zero-Risk Cleanups (~15-25% speedup)
Không ảnh hưởng accuracy, chỉ loại bỏ thừa:

1. **Xóa `resize_3x_enhanced`** (line 476 `preprocess_variants`) - trùng y hệt `resize_3x`
2. **Cache CLAHE objects ở module level** - tạo 1 lần, dùng lại cho mọi crop
   ```python
   # Module level (top of file)
   _CLAHE_30 = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
   _CLAHE_50 = cv2.createCLAHE(clipLimit=5.0, tileGridSize=(8,8))
   _CLAHE_80 = cv2.createCLAHE(clipLimit=8.0, tileGridSize=(8,8))
   ```
3. **Cache `GaussianBlur` và `adaptiveThreshold` results** - tính 1 lần trong `find_qr_candidates()`, truyền vào `extract_qr_focused_regions()` và `find_finder_patterns()` thay vì recompute

### Tier 2 - Smart Ordering (~30-50% speedup trên ảnh dễ)
Sắp xếp lại thứ tự để early exit kick in sớm hơn:

1. **Reorder preprocessing variants** - đưa winners lên đầu:
   ```
   Thứ tự mới: resize_3x, resize_3x_adapt, resize_4x, resize_3x_otsu, ...
   (resize_3x và resize_3x_adapt là 2 trong 3 winning variants)
   ```
2. **Reorder crops** trong detection loop:
   - QR-focused regions → finder_pattern → contours → grid → full image
   - (Hiện tại full image và grid chạy cùng lúc với QR-focused)
3. **Defer `bilateralFilter`** - chuyển về cuối variant list (chỉ chạy nếu chưa có match)

### Tier 3 - Parallel Decode với Early-Cancel (~2-4x speedup trên ảnh khó)

**Ý tưởng:** Tách ~683 decode attempts thành N chunks, mỗi chunk chạy trên 1 thread. Thread nào tìm ra kết quả đầu tiên → set shared event → các threads còn lại tự dừng.

**Tại sao ThreadPoolExecutor hoạt động thực sự parallel ở đây:**  
zxingcpp là C extension → trong khi C code chạy, Python GIL được release → nhiều threads cùng decode song song.

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Event
import math

def _decode_chunk(chunk: list[np.ndarray], stop_event: Event) -> str | None:
    """Decode một chunk tuần tự, kiểm tra stop_event sau mỗi attempt."""
    for img in chunk:
        if stop_event.is_set():
            return None  # thread khác đã tìm ra kết quả, dừng lại
        result = try_decode_qr_only(img)
        if result:
            return result
    return None

def try_decode_parallel(all_variants: list[np.ndarray], n_threads: int = 3) -> str | None:
    """
    Tách all_variants thành n_threads chunks, chạy song song.
    Thread nào decode thành công đầu tiên → dừng toàn bộ threads còn lại.
    """
    if not all_variants:
        return None

    stop_event = Event()
    chunk_size = math.ceil(len(all_variants) / n_threads)
    chunks = [all_variants[i:i + chunk_size] for i in range(0, len(all_variants), chunk_size)]

    with ThreadPoolExecutor(max_workers=n_threads) as executor:
        futures = [
            executor.submit(_decode_chunk, chunk, stop_event)
            for chunk in chunks
        ]
        for future in as_completed(futures):
            result = future.result()
            if result:
                stop_event.set()          # báo hiệu dừng các threads khác
                executor.shutdown(wait=False, cancel_futures=True)
                return result

    return None
```

**Ví dụ với 600 attempts và 3 threads:**
```
Thread 1: attempt 0-199    ← decode tuần tự
Thread 2: attempt 200-399  ← decode tuần tự (song song với T1, T2)
Thread 3: attempt 400-599  ← decode tuần tự

→ Nếu attempt #50 là winner: Thread 1 tìm ra ở attempt 50,
  set stop_event → Thread 2, 3 dừng sau attempt hiện tại → return kết quả
→ Tổng thời gian ≈ 50 attempts (thay vì 50 + thêm 550 remaining)
```

**Số threads tối ưu:**
- `n_threads=3`: Balance CPU usage vs overhead cho hầu hết servers
- `n_threads=4`: Nếu server có 4+ cores và Celery worker có đủ CPU

---

## Files Cần Sửa

| File | Thay đổi |
|------|---------|
| [main.py](../main.py) | Mọi thay đổi tối ưu (module-level CLAHE, reorder, parallel loop) |

Không cần thêm dependency mới (ThreadPoolExecutor là stdlib).

---

## Thứ Tự Thực Hiện

1. **Tier 1** trước - safe, verify 3/8 vẫn pass
2. **Tier 2** - reorder và defer bilateralFilter, verify lại
3. **Tier 3** - thêm parallel decode, measure speedup

---

## Verification

```bash
# Đo thời gian baseline trước khi sửa
time python main.py --test_dir test_images/

# Sau mỗi tier, chạy lại và so sánh
python main.py --test_dir test_images/ 2>&1 | grep -E "(CCCD|Kết quả|success)"
```

Expected results:
- Accuracy: 3/8 (37.5%) không đổi
- Tier 1: ~20% giảm thời gian
- Tier 2: thêm ~40% giảm trên CCCD_1, 7, 8 (ảnh dễ - early exit sớm hơn)
- Tier 3: thêm ~50% giảm trên CCCD_2-6 (ảnh khó, nhiều attempts)

---

## Không làm

- Thay đổi preprocessing logic (giữ accuracy)
- Bỏ bất kỳ variant nào ngoài duplicate `resize_3x_enhanced`
- Thêm thư viện mới
