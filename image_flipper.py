#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图片翻转处理工具
================

支持以下翻转变换（与 index.html 中浏览器端 EXIF 校正 / 手动旋转逻辑一致）：

变换方式
--------
1. EXIF 自动校正（根据 JPEG 的 EXIF Orientation 标签自动摆正）
2. 手动旋转：90° / 180° / 270°（顺时针 / 逆时针）
3. 水平镜像翻转（左→右）
4. 垂直翻转（上→下）
5. EXIF 自动校正 + 手动旋转叠加（与网页 OCR 面板"已自动校正 + 手动 N°"的语义一致）

使用示例
--------
# 仅 EXIF 自动校正
python image_flipper.py input.jpg -m exif -o output.jpg

# EXIF 校正后再顺时针转 180°（对应参考图第 1 张：EXIF 逆时针90° + 手动180°）
python image_flipper.py input.jpg -m "exif+180" -o output.jpg

# 水平镜像翻转
python image_flipper.py input.jpg -m horizontal -o output.jpg

# 顺时针旋转 90°
python image_flipper.py input.jpg -m 90cw -o output.jpg

# 批量处理：当前目录下所有 jpg 都顺时针转 90°
python image_flipper.py --batch *.jpg -m 90cw -o ./out

模式一览
--------
exif            EXIF 自动校正
exif+90         EXIF + 顺时针 90°
exif+180        EXIF + 顺时针 180°
exif+270        EXIF + 顺时针 270°
horizontal / h  水平镜像翻转（左→右）
vertical / v    垂直翻转（上→下）
90cw            顺时针旋转 90°
90ccw           逆时针旋转 90°
180             旋转 180°
270cw           顺时针旋转 270°
"""

import argparse
import glob
import sys
from pathlib import Path

try:
    from PIL import Image, ImageOps
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


# ---------- 变换实现 ----------

def apply_exif_correction(img):
    """根据 EXIF Orientation 标签自动校正图片方向（Pillow 内置可靠实现）"""
    return ImageOps.exif_transpose(img)


def rotate_cw(img, degrees):
    """顺时针旋转指定角度（90/180/270）。Pillow 中 ROTATE_270=顺时针90°，ROTATE_90=逆时针90°。"""
    table = {
        0: lambda x: x.copy(),
        90: lambda x: x.transpose(Image.ROTATE_270),
        180: lambda x: x.transpose(Image.ROTATE_180),
        270: lambda x: x.transpose(Image.ROTATE_90),
    }
    if degrees not in table:
        raise ValueError(f"不支持的旋转角度：{degrees}（仅支持 0/90/180/270）")
    return table[degrees](img)


def flip_horizontal(img):
    """水平镜像翻转（左→右）"""
    return img.transpose(Image.FLIP_LEFT_RIGHT)


def flip_vertical(img):
    """垂直翻转（上→下）"""
    return img.transpose(Image.FLIP_TOP_BOTTOM)


# ---------- 单图处理 ----------

def process_image(input_path, mode, output_path=None):
    """根据模式处理单张图片，返回输出路径"""
    if not HAS_PIL:
        print("错误：缺少 Pillow 库。请运行：pip install Pillow", file=sys.stderr)
        sys.exit(1)

    input_path = Path(input_path)
    if not input_path.exists():
        print(f"错误：输入文件不存在：{input_path}", file=sys.stderr)
        return None

    img = Image.open(input_path)

    # 解析模式
    if mode == 'exif':
        result = apply_exif_correction(img)
        desc = 'EXIF 自动校正'
    elif mode.startswith('exif+'):
        try:
            extra = int(mode[5:])
        except ValueError:
            print(f"错误：exif+ 模式后必须跟角度，例如 exif+180（当前：{mode}）", file=sys.stderr)
            return None
        result = apply_exif_correction(img)
        result = rotate_cw(result, extra)
        desc = f'EXIF 自动校正 + 顺时针 {extra}°'
    elif mode in ('horizontal', 'h'):
        result = flip_horizontal(img)
        desc = '水平镜像翻转'
    elif mode in ('vertical', 'v'):
        result = flip_vertical(img)
        desc = '垂直翻转'
    elif mode == '90cw':
        result = rotate_cw(img, 90)
        desc = '顺时针旋转 90°'
    elif mode == '90ccw':
        result = rotate_cw(img, 270)
        desc = '逆时针旋转 90°（= 顺时针 270°）'
    elif mode == '180':
        result = rotate_cw(img, 180)
        desc = '旋转 180°'
    elif mode == '270cw':
        result = rotate_cw(img, 270)
        desc = '顺时针旋转 270°'
    else:
        print(f"错误：不支持的模式 '{mode}'。可用：exif / exif+N / horizontal / vertical / 90cw / 90ccw / 180 / 270cw", file=sys.stderr)
        return None

    # 确定输出路径
    if output_path is None:
        stem = input_path.stem
        suffix = input_path.suffix
        output_path = input_path.parent / f"{stem}_flipped{suffix}"
    else:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

    # 保存：经 exif_transpose 后 EXIF Orientation 已被自动去除（避免浏览器/查看器二次旋转）
    result.save(output_path)

    print(f"✓ {desc}")
    print(f"  输入：{input_path}  ({img.size[0]}x{img.size[1]})")
    print(f"  输出：{output_path}  ({result.size[0]}x{result.size[1]})")
    return output_path


# ---------- 入口 ----------

def build_arg_parser():
    p = argparse.ArgumentParser(
        description='图片翻转处理工具 - EXIF 自动校正 + 手动旋转 / 镜像翻转',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument('input', nargs='+', help='输入图片路径（可传多个；支持通配符 *.jpg）')
    p.add_argument('-o', '--output', help='输出路径（单文件：完整路径；批量：目录路径）')
    p.add_argument('-m', '--mode', required=True,
                   help='翻转模式：exif / exif+90 / exif+180 / exif+270 / '
                        'horizontal / vertical / 90cw / 90ccw / 180 / 270cw')
    return p


def main():
    args = build_arg_parser().parse_args()

    # 展开通配符 + 去重保序
    inputs = []
    for token in args.input:
        matched = glob.glob(token) if any(c in token for c in '*?[') else [token]
        inputs.extend(matched)
    seen = set()
    inputs = [p for p in inputs if not (p in seen or seen.add(p))]

    if not inputs:
        print("错误：未找到任何输入文件", file=sys.stderr)
        sys.exit(1)

    out_arg = Path(args.output) if args.output else None
    is_batch = len(inputs) > 1 or (out_arg and out_arg.is_dir())

    ok = 0
    for src in inputs:
        src_path = Path(src)
        if is_batch:
            target_dir = out_arg if (out_arg and out_arg.is_dir()) else (out_arg or src_path.parent)
            target_dir = Path(target_dir)
            target_dir.mkdir(parents=True, exist_ok=True)
            out_path = target_dir / f"{src_path.stem}_flipped{src_path.suffix}"
        else:
            out_path = out_arg
        result = process_image(src_path, args.mode, out_path)
        if result:
            ok += 1
        print()

    print(f"处理完成：{ok}/{len(inputs)} 张成功")
    sys.exit(0 if ok == len(inputs) else 2)


if __name__ == '__main__':
    main()