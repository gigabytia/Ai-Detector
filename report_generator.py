"""
Генерация HTML-отчёта по аналитике трекинга поз.
"""
import os
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def _sec_to_hms(sec: float) -> str:
    sec = int(sec or 0)
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def _format_pose_name(pose: str) -> str:
    mapping = {
        "standing": "Стоит",
        "sitting": "Сидит",
        "hand_raised": "Рука поднята",
        "unknown": "Неизвестно",
    }
    return mapping.get(pose, pose)


def generate_html_report(summary: dict, output_dir: str = "reports") -> str:
    """
    Генерирует HTML-отчёт и возвращает путь к нему.
    """
    os.makedirs(output_dir, exist_ok=True)

    meta = summary["meta"]
    kpi = summary["kpi"]

    timeline_df = pd.DataFrame(summary.get("timeline", []))
    tracks_df = pd.DataFrame(summary.get("track_summary", []))
    events_df = pd.DataFrame(summary.get("events", []))

    all_detections = []
    for frame in summary.get("frames", []):
        for det in frame.get("detections", []):
            all_detections.append(det)

    det_df = pd.DataFrame(all_detections) if all_detections else pd.DataFrame()

    # ─────────────────────────────────────────────
    # График: количество людей по времени
    # ─────────────────────────────────────────────
    if not timeline_df.empty:
        fig_people = px.line(
            timeline_df,
            x="timestamp_sec",
            y="total_people",
            title="Количество людей по времени",
            labels={"timestamp_sec": "Время, сек", "total_people": "Людей"},
        )
        fig_people.update_traces(line=dict(width=3, color="royalblue"))
        people_chart_html = fig_people.to_html(full_html=False, include_plotlyjs=False)
    else:
        people_chart_html = "<p>Нет данных для графика количества людей.</p>"

    # ─────────────────────────────────────────────
    # График: позы по времени
    # ─────────────────────────────────────────────
    if not timeline_df.empty:
        fig_pose = go.Figure()

        for col, name, color in [
            ("standing", "Стоит", "green"),
            ("sitting", "Сидит", "orange"),
            ("hand_raised", "Рука поднята", "red"),
            ("unknown", "Неизвестно", "gray"),
        ]:
            if col in timeline_df.columns:
                fig_pose.add_trace(go.Scatter(
                    x=timeline_df["timestamp_sec"],
                    y=timeline_df[col],
                    mode="lines",
                    name=name,
                    line=dict(color=color, width=2),
                ))

        fig_pose.update_layout(
            title="Распределение поз по времени",
            xaxis_title="Время, сек",
            yaxis_title="Количество",
            hovermode="x unified",
        )
        pose_chart_html = fig_pose.to_html(full_html=False, include_plotlyjs=False)
    else:
        pose_chart_html = "<p>Нет данных для графика поз.</p>"

    # ─────────────────────────────────────────────
    # Диаграмма: общая доля поз
    # ─────────────────────────────────────────────
    pose_counts = {
        "Стоит": kpi.get("standing_detections", 0),
        "Сидит": kpi.get("sitting_detections", 0),
        "Рука поднята": kpi.get("hand_raised_detections", 0),
        "Неизвестно": kpi.get("unknown_detections", 0),
    }

    if sum(pose_counts.values()) > 0:
        fig_pie = px.pie(
            names=list(pose_counts.keys()),
            values=list(pose_counts.values()),
            title="Общее распределение поз",
            color=list(pose_counts.keys()),
            color_discrete_map={
                "Стоит": "green",
                "Сидит": "orange",
                "Рука поднята": "red",
                "Неизвестно": "gray",
            }
        )
        pie_chart_html = fig_pie.to_html(full_html=False, include_plotlyjs=False)
    else:
        pie_chart_html = "<p>Нет данных для круговой диаграммы.</p>"

    # ─────────────────────────────────────────────
    # Heatmap положений людей
    # ─────────────────────────────────────────────
    if not det_df.empty and {"center_x", "center_y"}.issubset(det_df.columns):
        fig_heat = px.density_heatmap(
            det_df,
            x="center_x",
            y="center_y",
            nbinsx=40,
            nbinsy=30,
            title="Тепловая карта положений людей",
            labels={"center_x": "X", "center_y": "Y"},
        )
        fig_heat.update_yaxes(autorange="reversed")
        heatmap_html = fig_heat.to_html(full_html=False, include_plotlyjs=False)
    else:
        heatmap_html = "<p>Нет данных для тепловой карты.</p>"

    # ─────────────────────────────────────────────
    # Таблица по ID
    # ─────────────────────────────────────────────
    if not tracks_df.empty:
        tracks_df = tracks_df.copy()
        tracks_df["first_seen"] = tracks_df["first_seen_sec"].apply(_sec_to_hms)
        tracks_df["last_seen"] = tracks_df["last_seen_sec"].apply(_sec_to_hms)
        tracks_df["duration"] = tracks_df["duration_sec"].apply(_sec_to_hms)
        tracks_df["dominant_pose"] = tracks_df["dominant_pose"].apply(_format_pose_name)

        tracks_table_html = tracks_df[[
            "track_id",
            "first_seen",
            "last_seen",
            "duration",
            "frames_seen",
            "dominant_pose",
            "hand_raise_events",
            "avg_center_x",
            "avg_center_y",
        ]].to_html(index=False)
    else:
        tracks_table_html = "<p>Нет данных по трекам.</p>"

    # ─────────────────────────────────────────────
    # Таблица событий
    # ─────────────────────────────────────────────
    if not events_df.empty:
        events_df = events_df.copy()
        events_df["time"] = events_df["timestamp_sec"].apply(_sec_to_hms)

        event_name_map = {
            "hand_raised_start": "Начало события: рука поднята"
        }
        events_df["event_type"] = events_df["event_type"].map(
            lambda x: event_name_map.get(x, x)
        )

        events_table_html = events_df[[
            "event_type",
            "track_id",
            "frame_number",
            "time",
            "center_x",
            "center_y",
        ]].to_html(index=False)
    else:
        events_table_html = "<p>События не зафиксированы.</p>"

    # ─────────────────────────────────────────────
    # HTML
    # ─────────────────────────────────────────────
    html = f"""
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Отчёт по анализу видео</title>
    <script src="https://cdn.plot.ly/plotly-2.30.0.min.js"></script>
    <style>
        body {{
            font-family: Arial, sans-serif;
            background: #f4f6f9;
            margin: 0;
            padding: 20px;
            color: #222;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}
        .block {{
            background: white;
            padding: 20px;
            margin-bottom: 20px;
            border-radius: 12px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.08);
        }}
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 15px;
        }}
        .kpi {{
            background: #ffffff;
            border-radius: 10px;
            padding: 16px;
            border: 1px solid #e6e9ef;
        }}
        .kpi-title {{
            font-size: 14px;
            color: #666;
        }}
        .kpi-value {{
            font-size: 28px;
            font-weight: bold;
            margin-top: 8px;
            color: #1e293b;
        }}
        h1, h2 {{
            margin-top: 0;
            color: #0f172a;
        }}
        p {{
            line-height: 1.5;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
        }}
        th, td {{
            border: 1px solid #ddd;
            padding: 8px;
            font-size: 14px;
            text-align: left;
        }}
        th {{
            background: #f1f5f9;
        }}
        .meta p {{
            margin: 6px 0;
        }}
    </style>
</head>
<body>
<div class="container">
    <div class="block">
        <h1>Отчёт по анализу видео</h1>
        <div class="meta">
            <p><b>Источник:</b> {meta.get("source", "-")}</p>
            <p><b>Статус:</b> {meta.get("status", "-")}</p>
            <p><b>Размер кадра:</b> {meta.get("frame_width", 0)} × {meta.get("frame_height", 0)}</p>
            <p><b>FPS:</b> {meta.get("fps", 0)}</p>
            <p><b>Обработано кадров:</b> {meta.get("total_frames_processed", 0)}</p>
            <p><b>Обработанная длительность:</b> {_sec_to_hms(meta.get("processed_duration_sec", 0))}</p>
            <p><b>Дата формирования отчёта:</b> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
        </div>
    </div>

    <div class="block">
        <h2>Ключевые метрики</h2>
        <div class="kpi-grid">
            <div class="kpi">
                <div class="kpi-title">Уникальных людей</div>
                <div class="kpi-value">{kpi.get("unique_people", 0)}</div>
            </div>
            <div class="kpi">
                <div class="kpi-title">Среднее людей на кадр</div>
                <div class="kpi-value">{kpi.get("avg_people_per_frame", 0):.2f}</div>
            </div>
            <div class="kpi">
                <div class="kpi-title">Максимум людей в кадре</div>
                <div class="kpi-value">{kpi.get("max_people_in_frame", 0)}</div>
            </div>
            <div class="kpi">
                <div class="kpi-title">События "рука поднята"</div>
                <div class="kpi-value">{kpi.get("hand_raise_events", 0)}</div>
            </div>
        </div>
    </div>

    <div class="block">
        <h2>Количество людей по времени</h2>
        {people_chart_html}
    </div>

    <div class="block">
        <h2>Распределение поз по времени</h2>
        {pose_chart_html}
    </div>

    <div class="block">
        <h2>Общее распределение поз</h2>
        {pie_chart_html}
    </div>

    <div class="block">
        <h2>Тепловая карта положений людей</h2>
        {heatmap_html}
    </div>

    <div class="block">
        <h2>Сводка по ID</h2>
        {tracks_table_html}
    </div>

    <div class="block">
        <h2>События</h2>
        {events_table_html}
    </div>
</div>
</body>
</html>
"""

    report_name = f"pose_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    report_path = os.path.join(output_dir, report_name)

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)

    return report_path