from __future__ import annotations

from copy import deepcopy
import os
from typing import Any


SCRIPT_BASE_DEFAULTS: dict[str, Any] = {
    "cloud_game_enabled": True,
    "browser_headless_enabled": True,
    "browser_headless_restart_on_not_logged_in": False,
    "after_finish": "Exit",
    "log_level": "INFO",
}


def _instance_options() -> list[dict[str, str]]:
    """Allow deployments to extend instance names without changing the UI code."""
    configured = os.getenv("MARCH7TH_INSTANCE_OPTIONS", "")
    values = [item.strip() for item in configured.split(",") if item.strip()]
    if not values:
        values = [
            "拟造花萼（金）",
            "拟造花萼（赤）",
            "凝滞虚影",
            "侵蚀隧洞",
            "饰品提取",
            "历战余响",
        ]
    return [{"label": value, "value": value} for value in values]


def _field(
    key: str,
    label: str,
    value_type: str,
    default: Any,
    description: str = "",
    options: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    item = {
        "key": key,
        "label": label,
        "type": value_type,
        "default": default,
        "description": description,
    }
    if options:
        item["options"] = options
    return item


SCRIPT_SETTING_GROUPS: list[dict[str, Any]] = [
    {
        "key": "power",
        "title": "体力",
        "description": "清体力、培养目标和支援角色。",
        "fields": [
            _field("power_enable", "启用清体力", "boolean", True),
            _field(
                "instance_type",
                "副本类型",
                "select",
                "侵蚀隧洞",
                options=_instance_options(),
            ),
            _field(
                "instance_name",
                "副本名称/目标",
                "text",
                "",
                "按脚本显示的副本名称填写；留空时使用副本类型默认目标。",
            ),
            _field("tp_before_instance", "清体力前传送至任意锚点", "boolean", False),
            _field("use_reserved_trailblaze_power", "使用后备开拓力", "boolean", False),
            _field("use_fuel", "使用燃料", "boolean", False),
            _field("merge_immersifier", "优先合成沉浸器", "boolean", False),
            _field("build_target_enable", "启用培养目标", "boolean", False),
            _field(
                "build_target_scheme",
                "培养目标识别方案",
                "select",
                "instance",
                options=[
                    {"label": "按副本名称", "value": "instance"},
                    {"label": "按掉落物", "value": "drop"},
                ],
            ),
            _field("echo_of_war_enable", "启用历战余响", "boolean", False),
            _field("borrow_enable", "启用支援角色", "boolean", True),
            _field("borrow_character_enable", "强制使用支援角色", "boolean", False),
            _field("borrow_scroll_times", "支援列表滚动次数", "number", 10, "范围 1-10。"),
        ],
    },
    {
        "key": "daily",
        "title": "日常",
        "description": "每日实训、奖励领取与活动检查。",
        "fields": [
            _field("daily_enable", "启用每日实训", "boolean", True),
            _field("daily_material_enable", "通过合成材料完成任务", "boolean", True),
            _field("daily_himeko_try_enable", "通过姬子试用完成任务", "boolean", False),
            _field("daily_memory_one_enable", "通过回忆一完成任务", "boolean", False),
            _field("reward_enable", "启用奖励领取", "boolean", True),
            _field("reward_dispatch_enable", "领取委托奖励", "boolean", True),
            _field("reward_mail_enable", "领取邮件奖励", "boolean", True),
            _field("reward_assist_enable", "领取支援奖励", "boolean", True),
            _field("reward_quest_enable", "领取每日实训奖励", "boolean", True),
            _field("reward_srpass_enable", "领取无名勋礼奖励", "boolean", True),
            _field("reward_redemption_code_enable", "领取兑换码奖励", "boolean", True),
            _field("reward_achievement_enable", "领取成就奖励", "boolean", False),
            _field("reward_message_enable", "领取短信奖励", "boolean", False),
            _field("activity_enable", "启用活动检测", "boolean", True),
            _field("activity_dailycheckin_enable", "每日签到", "boolean", True),
            _field("activity_gardenofplenty_enable", "花藏繁生", "boolean", False),
            _field("activity_realmofthestrange_enable", "异器盈界", "boolean", False),
            _field("activity_planarfissure_enable", "位面分裂", "boolean", False),
        ],
    },
    {
        "key": "currencywars",
        "title": "货币战争",
        "description": "货币战争积分奖励与策略。",
        "fields": [
            _field("currencywars_enable", "启用货币战争积分奖励", "boolean", False),
            _field(
                "currencywars_type",
                "类别",
                "select",
                "overclock",
                options=[
                    {"label": "标准博弈", "value": "normal"},
                    {"label": "超频博弈", "value": "overclock"},
                ],
            ),
            _field(
                "currencywars_rank_difficulty",
                "职级难度",
                "select",
                "lowest",
                options=[
                    {"label": "最高职级", "value": "highest"},
                    {"label": "当前职级", "value": "current"},
                    {"label": "最低职级", "value": "lowest"},
                ],
            ),
            _field("currencywars_bonus_enable", "自动执行位面饰品快速提取", "boolean", False),
            _field("currencywars_fast_mode", "启用速通模式", "boolean", True),
            _field(
                "currencywars_strategy",
                "货币战争策略",
                "select",
                "default",
                options=[
                    {"label": "默认", "value": "default"},
                    {"label": "阿格莱雅", "value": "aglaea"},
                    {"label": "希儿（测试版）", "value": "seele"},
                ],
            ),
            _field(
                "currencywars_remembrance_trailblazer_name",
                "开拓者·记忆名称",
                "text",
                "",
                "仅在使用相关策略时填写游戏内实际名称。",
            ),
            _field("currencywars_strategy_restart_on_special_tags", "遇到特定词条时接受重开", "boolean", True),
        ],
    },
    {
        "key": "universe",
        "title": "差分宇宙",
        "description": "差分宇宙积分和模拟宇宙相关选项。",
        "fields": [
            _field("weekly_divergent_enable", "启用差分宇宙积分奖励", "boolean", True),
            _field(
                "weekly_divergent_type",
                "积分模式",
                "select",
                "normal",
                options=[
                    {"label": "常规演算", "value": "normal"},
                    {"label": "周期演算", "value": "cycle"},
                ],
            ),
            _field("weekly_divergent_level", "难度等级", "number", 5, "范围 1-6。"),
            _field("weekly_divergent_bonus_enable", "积分完成后自动饰品提取", "boolean", False),
            _field("weekly_divergent_stable_mode", "启用低性能兼容模式", "boolean", False),
            _field("universe_enable", "启用模拟宇宙/差分宇宙", "boolean", False),
            _field(
                "universe_category",
                "类别",
                "select",
                "divergent",
                options=[
                    {"label": "差分宇宙", "value": "divergent"},
                    {"label": "模拟宇宙", "value": "universe"},
                ],
            ),
            _field(
                "universe_frequency",
                "运行频率",
                "select",
                "weekly",
                options=[
                    {"label": "每周", "value": "weekly"},
                    {"label": "每天", "value": "daily"},
                ],
            ),
            _field("universe_count", "运行次数", "number", 34, "范围 0-34，0 表示不指定。"),
            _field("universe_timeout", "运行超时（小时）", "number", 20, "范围 1-24。"),
            _field("universe_difficulty", "模拟宇宙难度", "number", 0, "范围 0-5，0 表示不配置。"),
        ],
    },
    {
        "key": "fight",
        "title": "锄大地",
        "description": "云游戏模式暂不支持此类任务，设置会保留但不会由 daily 启动。",
        "fields": [
            _field("fight_enable", "启用锄大地", "boolean", False),
            _field("fight_timeout", "锄大地超时（小时）", "number", 12, "范围 1-24。"),
            _field("fight_team_enable", "锄大地自动切换队伍", "boolean", False),
            _field(
                "fight_map_version",
                "地图版本",
                "select",
                "不配置",
                options=[
                    {"label": "不配置", "value": "不配置"},
                    {"label": "默认（疾跑）", "value": "default"},
                    {"label": "黄泉专用", "value": "HuangQuan"},
                ],
            ),
            _field(
                "fight_main_map",
                "优先星球",
                "select",
                "0",
                options=[
                    {"label": "不配置", "value": "0"},
                    {"label": "空间站", "value": "1"},
                    {"label": "雅利洛", "value": "2"},
                    {"label": "仙舟", "value": "3"},
                    {"label": "匹诺康尼", "value": "4"},
                    {"label": "翁法罗斯", "value": "5"},
                ],
            ),
        ],
    },
    {
        "key": "cloud",
        "title": "云游戏",
        "description": "云崩铁登录、浏览器和排队设置。",
        "fields": [
            _field("cloud_game_enable", "使用云·星穹铁道", "boolean", True),
            _field("cloud_game_fullscreen_enable", "全屏运行", "boolean", False),
            _field("cloud_game_use_paid_time", "使用付费时长", "boolean", False),
            _field("cloud_game_max_queue_time", "最大排队等待时间（分钟）", "number", 60, "范围 1-120。"),
            _field("cloud_game_login_timeout", "登录超时时间（分钟）", "number", 20, "范围 1-120。"),
            _field(
                "browser_type",
                "浏览器类型",
                "select",
                "integrated",
                options=[
                    {"label": "集成 Chrome", "value": "integrated"},
                    {"label": "Chrome", "value": "chrome"},
                    {"label": "Edge", "value": "edge"},
                ],
            ),
            _field("browser_headless_enable", "启用无窗口模式", "boolean", True),
            _field("browser_headless_restart_on_not_logged_in", "未登录时自动切换为有窗口模式", "boolean", False),
            _field("browser_persistent_enable", "保存浏览器登录状态", "boolean", True),
            _field("browser_download_use_mirror", "使用国内镜像下载浏览器和驱动", "boolean", True),
            _field("browser_scale_factor", "浏览器缩放比例", "number", 1.0, "建议 0.5-2.0。"),
        ],
    },
    {
        "key": "program",
        "title": "程序",
        "description": "运行结束行为、日志和循环相关设置。",
        "fields": [
            _field(
                "log_level",
                "日志等级",
                "select",
                "INFO",
                options=[
                    {"label": "简洁（INFO）", "value": "INFO"},
                    {"label": "详细（DEBUG）", "value": "DEBUG"},
                ],
            ),
            _field("pause_after_success", "成功后暂停程序", "boolean", True),
            _field("exit_after_failure", "失败后直接退出", "boolean", True),
            _field(
                "after_finish",
                "任务完成后",
                "select",
                "Exit",
                options=[
                    {"label": "无操作", "value": "None"},
                    {"label": "退出", "value": "Exit"},
                    {"label": "循环", "value": "Loop"},
                ],
            ),
            _field(
                "loop_mode",
                "循环模式",
                "select",
                "scheduled",
                options=[
                    {"label": "定时任务", "value": "scheduled"},
                    {"label": "根据开拓力", "value": "power"},
                ],
            ),
            _field("power_limit", "循环所需最低开拓力", "number", 160, "范围 10-300。"),
            _field("refresh_hour", "游戏刷新时间（小时）", "number", 4, "范围 0-23。"),
            _field("play_audio", "完成后播放提示音", "boolean", False),
        ],
    },
    {
        "key": "notification",
        "title": "推送",
        "description": "这里只开放通知偏好，不开放机器人密钥和账号信息。",
        "fields": [
            _field("notification_enable", "启用消息推送", "boolean", True),
            _field(
                "notify_level",
                "通知级别",
                "select",
                "all",
                options=[
                    {"label": "推送所有通知", "value": "all"},
                    {"label": "仅推送错误", "value": "error"},
                ],
            ),
            _field("notify_merge", "合并完整运行通知", "boolean", False),
            _field("notify_send_images", "推送截图", "boolean", True),
        ],
    },
    {
        "key": "misc",
        "title": "杂项",
        "description": "自动战斗、OCR 和截图行为。",
        "fields": [
            _field("auto_battle_detect_enable", "启用自动战斗和二倍速检测", "boolean", True),
            _field(
                "ocr_gpu_acceleration",
                "OCR 加速模式",
                "select",
                "cpu",
                options=[
                    {"label": "自动", "value": "auto"},
                    {"label": "GPU", "value": "gpu"},
                    {"label": "DirectML", "value": "onnx_dml"},
                    {"label": "CPU", "value": "cpu"},
                    {"label": "OpenVINO CPU", "value": "openvino_cpu"},
                    {"label": "ONNX CPU", "value": "onnx_cpu"},
                ],
            ),
            _field("auto_set_resolution_enable", "自动修改分辨率", "boolean", True),
            _field("auto_set_game_path_enable", "自动配置游戏路径", "boolean", True),
            _field("use_background_screenshot", "优先使用后台截图", "boolean", True),
        ],
    },
]


SCRIPT_SETTING_DEFINITIONS = {
    field["key"]: field
    for group in SCRIPT_SETTING_GROUPS
    for field in group["fields"]
}
SAFE_SCRIPT_SETTING_KEYS = set(SCRIPT_SETTING_DEFINITIONS)


def normalize_script_overrides(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, Any] = {}
    for key, raw in value.items():
        definition = SCRIPT_SETTING_DEFINITIONS.get(str(key))
        if definition is None:
            continue
        value_type = definition["type"]
        if value_type == "boolean" and isinstance(raw, bool):
            result[str(key)] = raw
        elif value_type == "number" and isinstance(raw, (int, float)) and not isinstance(raw, bool):
            result[str(key)] = raw
        elif value_type in {"text", "select"} and isinstance(raw, str):
            allowed = {item["value"] for item in definition.get("options", [])}
            if value_type == "text" or not allowed or raw in allowed:
                result[str(key)] = raw
    return result


def normalized_script_settings(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    result = deepcopy(SCRIPT_BASE_DEFAULTS)
    for key in SCRIPT_BASE_DEFAULTS:
        if key in raw and isinstance(raw[key], str | bool):
            result[key] = raw[key]
    result["config_overrides"] = normalize_script_overrides(raw.get("config_overrides"))
    return result


def script_schema() -> dict[str, Any]:
    return {
        "groups": deepcopy(SCRIPT_SETTING_GROUPS),
        "safe_keys": sorted(SAFE_SCRIPT_SETTING_KEYS),
    }
