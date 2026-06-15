from __future__ import annotations

from scripts.profile import DEFAULT_CHARACTER_NAME, DEFAULT_FGIMAGE_TARGET, DEFAULT_USER_NAME


DEFAULT_VL_MODEL = "qwen3-vl-flash"
DEFAULT_EXPRESSION_LAYERS = [1717, 1475, 1261]
GENERATED_AVATAR_SCALE = 5.0

DEFAULT_CHARACTER_OPTIONS = {
    "appearance_groups": {
        "发色": ["黑发", "棕发", "金发", "银白发", "粉发"],
        "瞳色": ["黑瞳", "棕瞳", "蓝瞳", "绿瞳", "紫瞳"],
        "发型": ["长直发", "短发", "中长发", "双马尾", "单马尾", "侧马尾", "波浪卷"],
        "服装": ["校服", "休闲私服", "针织衫", "衬衫短裙", "运动服", "连衣裙"],
        "整体风格": ["清纯", "可爱", "冷淡", "优雅", "活泼"],
    },
    "appearance_traits": [],
    "personality_traits": [
        "傲娇系",
        "三无冷淡系",
        "呆萌系",
        "元气少女系",
        "温柔治愈系",
        "毒舌系",
        "害羞内向系",
        "天然系",
        "认真优等生系",
        "慵懒系",
    ],
    "identity_traits": [],
    "styles": ["anime_desktop_pet", "transparent_png", "live2d_like"],
    "defaults": {
        "appearance_traits": ["棕发", "蓝瞳", "中长发", "校服", "清纯"],
        "personality_traits": ["温柔治愈系", "认真优等生系"],
        "identity_traits": [],
        "personality_dimensions": {"温柔治愈系": 4, "认真优等生系": 3},
        "appearance_style_dimensions": {"清纯": 4},
        "style": "anime_desktop_pet",
    },
}

DEFAULT_CHARACTER_OPTIONS["appearance_traits"] = [
    trait
    for traits in DEFAULT_CHARACTER_OPTIONS["appearance_groups"].values()
    for trait in traits
]
