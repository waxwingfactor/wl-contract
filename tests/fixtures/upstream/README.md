# Upstream Wayland regression fixtures

Retrieved from the public Wayland mirror on 2026-10-15. Both XML files are
unmodified upstream bytes and retain their original copyright and license.
They are a revision pair, not an input bundle: compare them as separate files.

The upstream change corrected the `blur` capability from zero to one in a
bitfield. Its author described this as technically breaking but already broken:
clients had been unable to receive the blur capability. This fixture proves
structural change detection; it is not evidence that working clients broke.

Commit explanation:
https://chromium.googlesource.com/external/anongit.freedesktop.org/git/wayland/wayland-protocols/+/efbc060534be948b63e1f395d69b583eebba3235

| File | Exact revision | SHA-256 |
| --- | --- | --- |
| [ext-background-effect.before.xml](https://raw.githubusercontent.com/wayland-mirror/wayland-protocols/0c79b5c96ff08338df143b91543619a86cce6500/staging/ext-background-effect/ext-background-effect-v1.xml) | `0c79b5c96ff08338df143b91543619a86cce6500` | `9aa5011f38752c0146014f8569f3d3981db7dbb8c04e578a80beef6c98fa9653` |
| [ext-background-effect.after.xml](https://raw.githubusercontent.com/wayland-mirror/wayland-protocols/efbc060534be948b63e1f395d69b583eebba3235/staging/ext-background-effect/ext-background-effect-v1.xml) | `efbc060534be948b63e1f395d69b583eebba3235` | `e463b7863c97d7be05489b52b15cd0b3a5d8290b51340f62023b47d03b4217e3` |

Reproduce from an installed package:

```console
wl-contract compare tests/fixtures/upstream/ext-background-effect.before.xml tests/fixtures/upstream/ext-background-effect.after.xml --format json
```

Expected: exit 1, verdict `incompatible`, and a `break` finding identifying the
`blur` enum entry changing from numeric zero to one. No compositor is started
and no upstream code is executed.
