import streamlit as st

THEME_CSS = """
<style>
    :root {
        --bg: #0b1020;
        --bg-2: #111827;
        --panel: rgba(15, 23, 42, 0.75);
        --panel-strong: rgba(17, 24, 39, 0.9);
        --border: rgba(148, 163, 184, 0.18);
        --primary: #6366f1;
        --primary-2: #8b5cf6;
        --accent: #14b8a6;
        --text: #f8fafc;
        --muted: #cbd5e1;
    }

    [data-testid="stAppViewContainer"] {
        background: radial-gradient(circle at top left, rgba(99,102,241,0.18), transparent 22%),
                    radial-gradient(circle at top right, rgba(20,184,166,0.12), transparent 18%),
                    var(--bg);
    }

    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, var(--bg-2), #0f172a);
    }

    .block-container {
        padding-top: 1.25rem;
        padding-bottom: 2.5rem;
        max-width: 1400px;
    }

    .task-board-kpi-grid,
    .home-card-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 0.9rem;
        margin: 1rem 0 1.2rem;
    }

    .home-card-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .stMetric {
        background: var(--panel);
        border: 1px solid var(--border);
        border-radius: 16px;
        padding: 0.8rem 1rem;
    }

    [data-testid="stMetricValue"] {
        font-size: 2rem;
        font-weight: 700;
        color: var(--text);
    }

    div[data-testid="stVerticalBlock"] > div {
        border-radius: 18px;
    }

    .stButton > button {
        border-radius: 12px !important;
        border: 1px solid rgba(99,102,241,0.45) !important;
        background: linear-gradient(135deg, var(--primary), var(--primary-2)) !important;
        color: var(--text) !important;
        font-weight: 600 !important;
        transition: filter 0.2s ease;
    }

    .stButton > button:hover {
        filter: brightness(1.08);
    }

    .stSelectbox > div > div,
    .stSlider > div,
    .stTextInput > div,
    .stTextArea > div,
    .stDateInput > div {
        border-radius: 12px !important;
    }

    .stAlert,
    .stInfo,
    .stSuccess,
    .stWarning,
    .stError {
        border-radius: 14px !important;
    }

    .stDataFrame {
        border-radius: 18px !important;
        overflow: hidden;
        border: 1px solid var(--border);
    }

    .app-hero,
    .task-board-header,
    .workspace-card,
    .feature-card {
        background: linear-gradient(135deg, rgba(99,102,241,0.18), rgba(20,184,166,0.08));
        border: 1px solid var(--border);
        border-radius: 20px;
        box-shadow: 0 12px 28px rgba(15, 23, 42, 0.18);
    }

    @media (max-width: 1200px) {
        .task-board-kpi-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
        }
    }

    @media (max-width: 768px) {
        .block-container {
            padding-left: 0.75rem;
            padding-right: 0.75rem;
        }

        .task-board-kpi-grid,
        .home-card-grid {
            grid-template-columns: 1fr;
        }

        [data-testid="stHorizontalBlock"] > div {
            width: 100% !important;
        }

        .stButton > button {
            width: 100% !important;
        }

        .app-hero,
        .task-board-header,
        .workspace-card,
        .feature-card {
            padding: 0.9rem !important;
        }
    }
</style>
"""


def apply_theme():
    st.markdown(THEME_CSS, unsafe_allow_html=True)
