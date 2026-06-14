# Test Media

## `cctv_fire_test.mp4`

CCTV-style fire test clip for Gemini/VLM policy testing.

- Source asset: Pexels video `25754152`, downloaded from `https://www.pexels.com/download/video/25754152/`
- Original source download was transformed into the smaller CCTV-style test clip below.
- Derived test clip: `cctv_fire_test.mp4`
- Preview frame: `cctv_fire_test_pexels_25754152_preview.jpg`
- License note: Pexels says its photos and videos can be downloaded and used for free, attribution is not required, and modification is allowed.

Suggested VLM args:

```json
{
  "prompt": "Detect whether visible flames or fire are present in this CCTV-style camera footage.",
  "target_labels": ["fire", "flame"],
  "video_path": "test_media/cctv_fire_test.mp4",
  "video_frame_count": 4,
  "video_frame_interval_seconds": 4,
  "provider": "gemini"
}
```
