from __future__ import annotations


API_BASE_URL = "https://maas-openapi.wanjiedata.com"
DESCRIPTION_MODEL = "deepseek-v4-flash"
IMAGE_MODEL = "gemini-3.1-flash-image-preview"
EMOTION_SPECS = {
    "happy": "开心，明亮笑容，眼神轻快，像刚刚收到用户夸奖",
    "angry": "生气，轻微鼓脸或皱眉，克制可爱，不要激烈攻击姿态",
    "shy": "害羞，脸红，视线稍微移开，动作内敛",
    "sad": "伤心，低落难过，眼神湿润但不要夸张哭喊",
}
REFERENCE_EMOTIONS = ("angry", "shy", "sad")
