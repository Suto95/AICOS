import streamlit as st

THEME_CSS = """
<style>
    :root {
        --bg: #090909;
        --bg-2: #121212;
        --panel: rgba(22, 13, 15, 0.82);
        --panel-strong: rgba(30, 17, 20, 0.92);
        --border: rgba(160, 32, 64, 0.35);
        --primary: #8e1d3a;
        --primary-2: #5d0d22;
        --accent: #a71f47;
        --text: #f6edf0;
        --muted: #d9c2c9;
    }

    [data-testid="stAppViewContainer"] {
        background: radial-gradient(circle at top left, rgba(142,29,58,0.18), transparent 28%),
                    radial-gradient(circle at top right, rgba(93,13,34,0.18), transparent 24%),
                    linear-gradient(135deg, #090909 0%, #151214 42%, #0d0c0c 100%);
    }

    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #140d10 0%, #090909 100%);
    }

    [data-testid="stHeader"] {
        background: rgba(9, 9, 9, 0.9) !important;
        border-bottom: 1px solid var(--border) !important;
        box-shadow: none !important;
    }

    [data-testid="stToolbar"] {
        background: rgba(9, 9, 9, 0.9) !important;
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

    html, body, [class*="css"], .stApp, .stMarkdown, .stTextInput, .stTextArea,
    .stSelectbox, .stSlider, .stDateInput, .stCaption, .stSubheader,
    .stHeader, .stTitle, .stParagraph, .stDataFrame, .stTabs, .stTab, p, span, div {
        color: var(--text) !important;
    }

    .stMarkdown p, .stMarkdown li, .stMarkdown h1, .stMarkdown h2, .stMarkdown h3, .stMarkdown h4,
    .stMarkdown h5, .stMarkdown h6, .stMarkdown strong, .stMarkdown em {
        color: var(--text) !important;
    }

    div[data-testid="stVerticalBlock"] > div {
        border-radius: 18px;
    }

    .stButton > button,
    .stDownloadButton > button,
    .stLinkButton > a,
    .stLinkButton > button,
    [data-testid="baseButton-primary"],
    [data-testid="baseButton-secondary"],
    [data-testid="stBaseButton-secondary"],
    [data-testid="stBaseButton-primary"],
    [data-testid="stLinkButton"] > a,
    [data-testid="stLinkButton"] > button {
        border-radius: 12px !important;
        border: 1px solid rgba(167, 31, 71, 0.52) !important;
        background: linear-gradient(135deg, var(--primary), var(--primary-2)) !important;
        color: var(--text) !important;
        font-weight: 600 !important;
        transition: filter 0.2s ease, transform 0.2s ease;
        box-shadow: none !important;
        text-decoration: none !important;
    }

    .stButton > button:hover,
    .stDownloadButton > button:hover,
    .stLinkButton > a:hover,
    .stLinkButton > button:hover,
    [data-testid="baseButton-primary"]:hover,
    [data-testid="baseButton-secondary"]:hover,
    [data-testid="stBaseButton-secondary"]:hover,
    [data-testid="stBaseButton-primary"]:hover,
    [data-testid="stLinkButton"] > a:hover,
    [data-testid="stLinkButton"] > button:hover {
        transform: translateY(-1px);
        filter: brightness(1.08);
    }

    [data-testid="stSidebar"] .stButton > button,
    [data-testid="stSidebar"] .stLinkButton > a,
    [data-testid="stSidebar"] [data-testid="baseButton-primary"],
    [data-testid="stSidebar"] [data-testid="baseButton-secondary"] {
        background: linear-gradient(135deg, var(--primary), var(--primary-2)) !important;
    }

    .stSelectbox > div > div,
    .stSlider > div,
    .stTextInput > div,
    .stTextArea > div,
    .stDateInput > div,
    .stNumberInput > div {
        border-radius: 12px !important;
    }

    [data-testid="stWidgetLabel"],
    [data-testid="stWidgetLabel"] label,
    [data-testid="stWidgetLabel"] p {
        color: var(--muted) !important;
        font-weight: 650 !important;
    }

    [data-baseweb="select"] > div,
    [data-baseweb="input"] > div,
    [data-baseweb="textarea"] textarea,
    [data-baseweb="base-input"] input,
    [data-testid="stNumberInput"] input {
        background: rgba(22, 13, 15, 0.92) !important;
        background-color: rgba(22, 13, 15, 0.92) !important;
        border: 1px solid rgba(160, 32, 64, 0.45) !important;
        color: var(--text) !important;
        box-shadow: none !important;
    }

    [data-testid="stSelectbox"] [data-baseweb="select"],
    [data-testid="stSelectbox"] [data-baseweb="select"] > div,
    [data-testid="stSelectbox"] [data-baseweb="select"] > div > div,
    [data-testid="stSelectbox"] [data-baseweb="select"] div[role="button"],
    [data-testid="stSelectbox"] input,
    [data-testid="stSelectbox"] [data-baseweb="base-input"],
    [data-testid="stSelectbox"] [data-baseweb="base-input"] > div {
        background: #160d0f !important;
        background-color: #160d0f !important;
        border-color: rgba(160, 32, 64, 0.52) !important;
        color: var(--text) !important;
        -webkit-text-fill-color: var(--text) !important;
        box-shadow: none !important;
    }

    [data-testid="stSelectbox"] [data-baseweb="select"] > div:hover,
    [data-testid="stSelectbox"] [data-baseweb="select"] > div:focus-within {
        background: #1e1114 !important;
        background-color: #1e1114 !important;
        border-color: rgba(167, 31, 71, 0.72) !important;
    }

    [data-baseweb="select"] span,
    [data-baseweb="select"] div,
    [data-baseweb="input"] input,
    [data-baseweb="textarea"] textarea,
    [data-testid="stNumberInput"] input {
        color: var(--text) !important;
        -webkit-text-fill-color: var(--text) !important;
    }

    [data-baseweb="select"] svg {
        color: var(--muted) !important;
        fill: var(--muted) !important;
    }

    [data-baseweb="popover"],
    [data-baseweb="menu"],
    [role="listbox"] {
        background: #160d0f !important;
        border: 1px solid rgba(160, 32, 64, 0.5) !important;
        color: var(--text) !important;
    }

    [data-baseweb="popover"] *,
    [data-baseweb="menu"] *,
    [role="listbox"] * {
        color: var(--text) !important;
        -webkit-text-fill-color: var(--text) !important;
    }

    [role="option"],
    [data-baseweb="menu"] li {
        background: #160d0f !important;
        color: var(--text) !important;
    }

    [role="option"]:hover,
    [role="option"][aria-selected="true"],
    [data-baseweb="menu"] li:hover {
        background: rgba(167, 31, 71, 0.34) !important;
        color: #ffffff !important;
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
        background: linear-gradient(135deg, rgba(142,29,58,0.18), rgba(93,13,34,0.12), rgba(20,16,18,0.82));
        border: 1px solid var(--border);
        border-radius: 20px;
        box-shadow: 0 12px 28px rgba(0, 0, 0, 0.32);
    }

    .bucket-section-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.75rem;
        min-height: 2.6rem;
        margin: 0.7rem 0 0.55rem;
        padding: 0.65rem 0.75rem;
        border: 1px solid rgba(160, 32, 64, 0.4);
        border-radius: 12px;
        background: linear-gradient(135deg, rgba(142,29,58,0.2), rgba(20,16,18,0.84));
        color: var(--text);
        font-size: 0.72rem;
        font-weight: 800;
        letter-spacing: 0.08em;
        text-transform: uppercase;
    }

    .bucket-section-header span {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-width: 1.65rem;
        height: 1.65rem;
        border-radius: 999px;
        background: rgba(167, 31, 71, 0.35);
        color: #ffffff !important;
        font-size: 0.78rem;
        letter-spacing: 0;
    }

    .task-card-title {
        color: var(--text) !important;
        font-size: 0.98rem;
        font-weight: 750;
        line-height: 1.35;
        margin-bottom: 0.45rem;
    }

    .task-card-meta {
        display: flex;
        flex-wrap: wrap;
        gap: 0.35rem;
        margin-bottom: 0.6rem;
    }

    .task-card-meta span {
        border: 1px solid rgba(160, 32, 64, 0.34);
        border-radius: 999px;
        background: rgba(9, 9, 9, 0.35);
        color: var(--muted) !important;
        font-size: 0.72rem;
        line-height: 1;
        padding: 0.28rem 0.42rem;
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
