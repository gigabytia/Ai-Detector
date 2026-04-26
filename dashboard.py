# ===== dashboard.py =====

from app import run_analysis
import tempfile
import os
import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

DB_PATH = "analytics.db"

st.set_page_config(
    page_title="Pose Analytics Dashboard",
    layout="wide"
)

st.title("Pose Analytics Dashboard")
tab1, tab2 = st.tabs(["Аналитика", "Новый анализ"])

# -------------------------
# Подключение к БД
# -------------------------
with tab1:
    conn = sqlite3.connect(DB_PATH)

    # -------------------------
    # Загрузка списка запусков
    # -------------------------
    runs = pd.read_sql(
        "SELECT id, source, created_at FROM runs ORDER BY id DESC",
        conn
    )

    if runs.empty:
        st.warning("В базе нет запусков.")
        st.stop()

    run_id = st.selectbox(
        "Выберите запуск",
        runs["id"],
        format_func=lambda x: f"Run {x}"
    )

    # -------------------------
    # KPI блок
    # -------------------------
    run_info = pd.read_sql(
        f"SELECT * FROM runs WHERE id={run_id}",
        conn
    ).iloc[0]

    timeline_df = pd.read_sql(
        f"SELECT * FROM timeline WHERE run_id={run_id}",
        conn
    )

    tracks_df = pd.read_sql(
        f"SELECT * FROM tracks WHERE run_id={run_id}",
        conn
    )

    events_df = pd.read_sql(
        f"SELECT * FROM events WHERE run_id={run_id}",
        conn
    )

    st.markdown("## Основные метрики")

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Обработано кадров", run_info["total_frames"])
    col2.metric("Длительность (сек)", round(run_info["duration_sec"], 2))
    col3.metric("FPS", round(run_info["fps"], 2))
    col4.metric("Уникальных людей", tracks_df["track_id"].nunique())

    st.divider()

    # -------------------------
    # График: Люди по времени
    # -------------------------
    st.markdown("## Люди по времени")

    fig_people = px.line(
        timeline_df,
        x="timestamp_sec",
        y="total_people",
        title="Количество людей",
    )

    st.plotly_chart(fig_people, use_container_width=True)

    # -------------------------
    # График: Позы по времени
    # -------------------------
    st.markdown("## Распределение поз")

    pose_columns = [
        "standing",
        "walking",
        "sitting",
        "lying",
        "hand_raised",
        "unknown"
    ]

    fig_pose = go.Figure()

    for col in pose_columns:
        if col in timeline_df.columns:
            fig_pose.add_trace(
                go.Scatter(
                    x=timeline_df["timestamp_sec"],
                    y=timeline_df[col],
                    mode="lines",
                    name=col
                )
            )

    fig_pose.update_layout(
        xaxis_title="Время (сек)",
        yaxis_title="Количество",
        hovermode="x unified"
    )

    st.plotly_chart(fig_pose, use_container_width=True)

    st.divider()

    # -------------------------
    # Heatmap
    # -------------------------
    st.markdown("## Тепловая карта перемещений")

    if not tracks_df.empty:
        # Получаем координаты через timeline join
        det_query = f"""
            SELECT t.timestamp_sec, e.center_x, e.center_y
            FROM events e
            JOIN runs r ON r.id = {run_id}
        """

    # Для простоты — строим heatmap по avg_center
    fig_heat = px.density_heatmap(
        tracks_df,
        x="avg_center_x",
        y="avg_center_y",
        nbinsx=40,
        nbinsy=30,
    )

    fig_heat.update_yaxes(autorange="reversed")

    st.plotly_chart(fig_heat, use_container_width=True)

    st.divider()

    # -------------------------
    # Таблица треков
    # -------------------------
    st.markdown("## Треки")

    st.dataframe(
        tracks_df.sort_values("track_id"),
        use_container_width=True
    )

    # -------------------------
    # Таблица событий
    # -------------------------
    st.markdown("## События")

    if events_df.empty:
        st.info("События отсутствуют.")
    else:
        st.dataframe(events_df, use_container_width=True)

    conn.close()

with tab2:

    st.markdown("## ▶ Запуск нового анализа")

    uploaded_file = st.file_uploader("Загрузите видео", type=["mp4", "avi", "mov"])

    model_choice = st.selectbox(
        "Выберите модель",
        ["yolov8n-pose.pt", "yolov8s-pose.pt"]
    )

    confidence = st.slider(
        "Confidence",
        min_value=0.1,
        max_value=0.9,
        value=0.25,
        step=0.05
    )

    inference_size = st.selectbox(
        "Размер инференса",
        [640, 960, 1280],
        index=1
    )

    if uploaded_file is not None:
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, uploaded_file.name)

        with open(temp_path, "wb") as f:
            f.write(uploaded_file.read())

        st.success("Видео загружено.")

        if st.button("🚀 Запустить анализ"):
            with st.spinner("Анализ выполняется..."):
                run_analysis(
                    video_source=temp_path,
                    model_name=model_choice,
                    confidence=confidence,
                    inference_size=inference_size
                )

            st.success("Анализ завершён! Обновите вкладку аналитики.")