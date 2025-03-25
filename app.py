import streamlit as st
import requests
import pandas as pd
import numpy as np
import datetime
import plotly.graph_objects as go
from datetime import timedelta
import re
from dateutil.relativedelta import relativedelta

# Page configuration
st.set_page_config(
    page_title="YouTube Performance Benchmark",
    page_icon="📊",
    layout="wide"
)

# Theme selection
theme = st.sidebar.radio("Theme", ["Light", "Dark"], horizontal=True)

# Set theme colors based on selection
if theme == "Dark":
    background_color = "#121212"
    text_color = "#FFFFFF"
    card_bg = "#1E1E1E"
    primary_color = "#BB86FC"
    secondary_color = "#03DAC6"
    gray_band_color = "rgba(100, 100, 100, 0.3)"
    line_color = "#FF4081"  # Accent color for highlight
    benchmark_color = "#BB86FC"  # Primary color for benchmark
    st.markdown("""
    <style>
        .stApp {
            background-color: #121212;
            color: #FFFFFF;
        }
        .main-header {color: #BB86FC !important;}
        .subheader {color: #03DAC6 !important;}
        .metric-card {background-color: #1E1E1E !important; color: #FFFFFF !important;}
        .success-box {background-color: #1E402D !important; color: #FFFFFF !important;}
        .info-box {background-color: #1A3C61 !important; color: #FFFFFF !important;}
    </style>
    """, unsafe_allow_html=True)
else:
    background_color = "#FFFFFF"
    text_color = "#000000"
    card_bg = "#F8F9FA"
    primary_color = "#6200EE"
    secondary_color = "#03DAC6"
    gray_band_color = "rgba(200, 200, 200, 0.5)"
    line_color = "#F50057"  # Accent color for highlight
    benchmark_color = "#6200EE"  # Primary color for benchmark

theme_colors = {
    'background_color': background_color,
    'text_color': text_color,
    'line_color': line_color,
    'benchmark_color': benchmark_color,
    'gray_band_color': gray_band_color,
    'primary_color': primary_color
}

# Custom CSS for better styling
st.markdown(f"""
<style>
    .main-header {{font-size: 2rem; font-weight: 600; margin-bottom: 1rem;}}
    .subheader {{font-size: 1.5rem; font-weight: 500; margin: 1rem 0;}}
    .success-box {{padding: 1rem; border-radius: 5px; margin: 1rem 0;}}
    .info-box {{padding: 1rem; border-radius: 5px; margin: 1rem 0;}}
    .metric-card {{padding: 1rem; border-radius: 5px; margin-bottom: 1rem; text-align: center;}}
</style>
""", unsafe_allow_html=True)

# Main title
st.markdown(f"<div class='main-header'>YouTube Performance Benchmark</div>", unsafe_allow_html=True)
st.markdown("Compare your video's performance against your channel's typical performance band")

# Safely load API key from secrets.toml
try:
    yt_api_key = st.secrets["YT_API_KEY"]
    if not yt_api_key:
        st.error("YouTube API Key is missing from secrets.toml!")
        st.stop()
except Exception as e:
    st.error(f"Error loading API key from secrets: {e}. Please check your secrets.toml file.")
    st.stop()

# ------------------------
# URL Parsing Functions
# ------------------------
def extract_channel_id(url):
    patterns = [
        r'youtube\.com/channel/([^/\s?]+)',
        r'youtube\.com/c/([^/\s?]+)',
        r'youtube\.com/user/([^/\s?]+)',
        r'youtube\.com/@([^/\s?]+)'
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            identifier = match.group(1)
            if pattern == patterns[0] and identifier.startswith('UC'):
                return identifier
            return get_channel_id_from_identifier(identifier, pattern)
    if url.strip().startswith('UC'):
        return url.strip()
    return None

def extract_video_id(url):
    patterns = [
        r'youtube\.com/watch\?v=([^&\s]+)',
        r'youtu\.be/([^?\s]+)',
        r'youtube\.com/embed/([^?\s]+)',
        r'youtube\.com/v/([^?\s]+)'
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    if re.match(r'^[A-Za-z0-9_-]{11}$', url.strip()):
        return url.strip()
    return None

def get_channel_id_from_identifier(identifier, pattern_used):
    try:
        if pattern_used == r'youtube\.com/channel/([^/\s?]+)':
            return identifier
        elif pattern_used == r'youtube\.com/c/([^/\s?]+)':
            search_url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&type=channel&q={identifier}&key={yt_api_key}"
        elif pattern_used == r'youtube\.com/user/([^/\s?]+)':
            username_url = f"https://www.googleapis.com/youtube/v3/channels?part=id&forUsername={identifier}&key={yt_api_key}"
            username_res = requests.get(username_url).json()
            if 'items' in username_res and username_res['items']:
                return username_res['items'][0]['id']
            search_url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&type=channel&q={identifier}&key={yt_api_key}"
        elif pattern_used == r'youtube\.com/@([^/\s?]+)':
            if identifier.startswith('@'):
                identifier = identifier[1:]
            search_url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&type=channel&q={identifier}&key={yt_api_key}"
        else:
            search_url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&type=channel&q={identifier}&key={yt_api_key}"
        if 'search_url' in locals():
            search_res = requests.get(search_url).json()
            if 'items' in search_res and search_res['items']:
                return search_res['items'][0]['id']['channelId']
    except Exception as e:
        st.error(f"Error resolving channel identifier: {e}")
    return None

# ------------------------
# Data Fetching Functions
# ------------------------
def fetch_channel_videos(channel_id, max_videos, api_key):
    playlist_url = f"https://www.googleapis.com/youtube/v3/channels?part=contentDetails,snippet,statistics&id={channel_id}&key={api_key}"
    try:
        playlist_res = requests.get(playlist_url).json()
        if 'items' not in playlist_res or not playlist_res['items']:
            st.error("Invalid Channel ID or no uploads found.")
            return None, None, None
        channel_info = playlist_res['items'][0]
        channel_name = channel_info['snippet']['title']
        channel_stats = channel_info['statistics']
        uploads_playlist_id = channel_info['contentDetails']['relatedPlaylists']['uploads']
        videos = []
        next_page_token = ""
        while (max_videos is None or len(videos) < max_videos) and next_page_token is not None:
            playlist_items_url = f"https://www.googleapis.com/youtube/v3/playlistItems?part=contentDetails,snippet&maxResults=50&playlistId={uploads_playlist_id}&key={api_key}"
            if next_page_token:
                playlist_items_url += f"&pageToken={next_page_token}"
            playlist_items_res = requests.get(playlist_items_url).json()
            for item in playlist_items_res.get('items', []):
                video_id = item['contentDetails']['videoId']
                title = item['snippet']['title']
                published_at = item['snippet']['publishedAt']
                videos.append({
                    'videoId': video_id,
                    'title': title,
                    'publishedAt': published_at
                })
                if max_videos is not None and len(videos) >= max_videos:
                    break
            next_page_token = playlist_items_res.get('nextPageToken')
        return videos, channel_name, channel_stats
    except Exception as e:
        st.error(f"Error fetching YouTube data: {e}")
        return None, None, None

def fetch_video_details(video_ids, api_key):
    if not video_ids:
        return {}
    all_details = {}
    video_chunks = [video_ids[i:i+50] for i in range(0, len(video_ids), 50)]
    for chunk in video_chunks:
        video_ids_str = ','.join(chunk)
        details_url = f"https://www.googleapis.com/youtube/v3/videos?part=contentDetails,statistics,snippet&id={video_ids_str}&key={api_key}"
        try:
            details_res = requests.get(details_url).json()
            for item in details_res.get('items', []):
                duration_str = item['contentDetails']['duration']
                duration_seconds = parse_duration(duration_str)
                published_at = item['snippet']['publishedAt']
                all_details[item['id']] = {
                    'duration': duration_seconds,
                    'viewCount': int(item['statistics'].get('viewCount', 0)),
                    'likeCount': int(item['statistics'].get('likeCount', 0)),
                    'commentCount': int(item['statistics'].get('commentCount', 0)),
                    'publishedAt': published_at,
                    'title': item['snippet']['title'],
                    'thumbnailUrl': item['snippet'].get('thumbnails', {}).get('medium', {}).get('url', ''),
                    'isShort': duration_seconds <= 120
                }
        except Exception as e:
            st.warning(f"Error fetching details for some videos: {e}")
    return all_details

def parse_duration(duration_str):
    hours = re.search(r'(\d+)H', duration_str)
    minutes = re.search(r'(\d+)M', duration_str)
    seconds = re.search(r'(\d+)S', duration_str)
    total_seconds = 0
    if hours:
        total_seconds += int(hours.group(1)) * 3600
    if minutes:
        total_seconds += int(minutes.group(1)) * 60
    if seconds:
        total_seconds += int(seconds.group(1))
    return total_seconds

def fetch_single_video(video_id, api_key):
    video_url = f"https://www.googleapis.com/youtube/v3/videos?part=snippet,statistics,contentDetails&id={video_id}&key={api_key}"
    try:
        response = requests.get(video_url).json()
        if 'items' not in response or not response['items']:
            return None
        video_data = response['items'][0]
        duration_str = video_data['contentDetails']['duration']
        duration_seconds = parse_duration(duration_str)
        return {
            'videoId': video_id,
            'title': video_data['snippet']['title'],
            'channelId': video_data['snippet']['channelId'],
            'channelTitle': video_data['snippet']['channelTitle'],
            'publishedAt': video_data['snippet']['publishedAt'],
            'thumbnailUrl': video_data['snippet'].get('thumbnails', {}).get('medium', {}).get('url', ''),
            'viewCount': int(video_data['statistics'].get('viewCount', 0)),
            'likeCount': int(video_data['statistics'].get('likeCount', 0)),
            'commentCount': int(video_data['statistics'].get('commentCount', 0)),
            'duration': duration_seconds,
            'isShort': duration_seconds <= 120
        }
    except Exception as e:
        st.error(f"Error fetching video details: {e}")
        return None

# ------------------------
# Benchmark & Simulation Functions
# ------------------------
def generate_historical_data(video_details, max_days, is_short=False):
    today = datetime.datetime.now().date()
    all_video_data = []
    for video_id, details in video_details.items():
        if is_short is not None and details['isShort'] != is_short:
            continue
        try:
            publish_date = datetime.datetime.fromisoformat(details['publishedAt'].replace('Z', '+00:00')).date()
            video_age_days = (today - publish_date).days
        except:
            continue
        if video_age_days < 3:
            continue
        days_to_generate = video_age_days if max_days > video_age_days else max_days
        total_views = details['viewCount']
        video_data = generate_view_trajectory(video_id, days_to_generate, total_views, details['isShort'])
        all_video_data.extend(video_data)
    if not all_video_data:
        return pd.DataFrame()
    return pd.DataFrame(all_video_data)

def generate_view_trajectory(video_id, days, total_views, is_short):
    data = []
    if is_short:
        trajectory = [total_views * (1 - np.exp(-5 * ((i+1)/days)**1.5)) for i in range(days)]
    else:
        k = 10
        trajectory = [total_views * (1 / (1 + np.exp(-k * ((i+1)/days - 0.35)))) for i in range(days)]
    scaling_factor = total_views / trajectory[-1] if trajectory[-1] > 0 else 1
    trajectory = [v * scaling_factor for v in trajectory]
    noise_factor = 0.05
    for i in range(days):
        noise = np.random.normal(0, noise_factor * total_views)
        if i == 0:
            noisy_value = max(100, trajectory[i] + noise)
        else:
            noisy_value = max(trajectory[i-1] + 10, trajectory[i] + noise)
        trajectory[i] = noisy_value
    daily_views = [trajectory[0]]
    for i in range(1, days):
        daily_views.append(trajectory[i] - trajectory[i-1])
    for day in range(days):
        data.append({
            'videoId': video_id,
            'day': day,
            'daily_views': int(daily_views[day]),
            'cumulative_views': int(trajectory[day])
        })
    return data

def calculate_benchmark(df, band_percentage):
    lower_q = (100 - band_percentage) / 200
    upper_q = 1 - (100 - band_percentage) / 200
    summary = df.groupby('day')['cumulative_views'].agg([
        ('lower_band', lambda x: x.quantile(lower_q)),
        ('upper_band', lambda x: x.quantile(upper_q)),
        ('median', 'median'),
        ('mean', 'mean'),
        ('count', 'count')
    ]).reset_index()
    return summary

def simulate_video_performance(video_data, benchmark_data, max_days, approach="full"):
    try:
        published_at = datetime.datetime.fromisoformat(video_data['publishedAt'].replace('Z', '+00:00')).date()
        current_date = datetime.datetime.now().date()
        days_since_publish = (current_date - published_at).days
    except:
        days_since_publish = 0
    current_views = video_data['viewCount']
    is_short = video_data['isShort']
    if days_since_publish < 2:
        days_since_publish = 2
    if approach == "full":
        days_to_project = max(days_since_publish, max_days)
    else:
        days_to_project = days_since_publish
    data = []
    if days_since_publish < len(benchmark_data):
        benchmark_views_at_current_age = benchmark_data.loc[days_since_publish, 'median']
        performance_ratio = current_views / benchmark_views_at_current_age if benchmark_views_at_current_age > 0 else 1.0
    else:
        performance_ratio = 1.0
    for day in range(days_since_publish + 1):
        if day >= len(benchmark_data):
            break
        if day == days_since_publish:
            cumulative_views = current_views
        else:
            benchmark_views = benchmark_data.loc[day, 'median']
            cumulative_views = benchmark_views * performance_ratio
        cumulative_views = int(cumulative_views * np.random.uniform(0.98, 1.02))
        if day == 0:
            daily_views = cumulative_views
        else:
            prev_cumulative = data[-1]['cumulative_views']
            daily_views = max(0, cumulative_views - prev_cumulative)
        data.append({
            'day': day,
            'daily_views': daily_views,
            'cumulative_views': cumulative_views,
            'projected': False
        })
    if days_to_project > days_since_publish and approach == "full":
        for day in range(days_since_publish + 1, days_to_project + 1):
            if day >= len(benchmark_data):
                break
            benchmark_views = benchmark_data.loc[day, 'median']
            projected_views = int(benchmark_views * performance_ratio)
            prev_cumulative = data[-1]['cumulative_views']
            daily_views = max(0, projected_views - prev_cumulative)
            data.append({
                'day': day,
                'daily_views': daily_views,
                'cumulative_views': projected_views,
                'projected': True
            })
    return pd.DataFrame(data)

def create_comparison_chart(benchmark_data, video_data, video_title, video_type_str, theme_colors, approach_mode="full"):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=benchmark_data['day'], 
        y=benchmark_data['upper_band'],
        name='Upper Band',
        mode='lines',
        line=dict(width=0),
        showlegend=False
    ))
    fig.add_trace(go.Scatter(
        x=benchmark_data['day'], 
        y=benchmark_data['lower_band'],
        name=f'Typical Performance Range ({video_type_str})',
        fill='tonexty',
        fillcolor=theme_colors['gray_band_color'],
        line=dict(width=0),
        mode='lines'
    ))
    fig.add_trace(go.Scatter(
        x=benchmark_data['day'], 
        y=benchmark_data['median'],
        name=f'Typical Performance ({video_type_str})',
        line=dict(color=theme_colors['benchmark_color'], width=2, dash='dash'),
        mode='lines'
    ))
    # For Approach 3, add an extra trace for the average of the band
    if approach_mode == "extra":
        avg_band = (benchmark_data['lower_band'] + benchmark_data['upper_band']) / 2
        fig.add_trace(go.Scatter(
            x=benchmark_data['day'],
            y=avg_band,
            name=f'Average of Typical Range ({video_type_str})',
            line=dict(color=theme_colors['primary_color'], width=2, dash='dot'),
            mode='lines'
        ))
        # And add a new trace for the channel's cumulative mean views
        fig.add_trace(go.Scatter(
            x=benchmark_data['day'],
            y=benchmark_data['mean'],
            name=f'Channel Cumulative Mean ({video_type_str})',
            line=dict(color=theme_colors['primary_color'], width=2, dash='longdash'),
            mode='lines'
        ))
    actual_data = video_data[video_data['projected'] == False]
    projected_data = video_data[video_data['projected'] == True]
    fig.add_trace(go.Scatter(
        x=actual_data['day'], 
        y=actual_data['cumulative_views'],
        name=f'"{video_title}" (Actual)',
        line=dict(color=theme_colors['line_color'], width=3),
        mode='lines'
    ))
    if not projected_data.empty:
        fig.add_trace(go.Scatter(
            x=projected_data['day'], 
            y=projected_data['cumulative_views'],
            name=f'"{video_title}" (Projected)',
            line=dict(color=theme_colors['line_color'], width=3, dash='dot'),
            mode='lines'
        ))
    fig.update_layout(
        title=f'Video Performance Comparison',
        xaxis_title='Days Since Upload',
        yaxis_title='Cumulative Views',
        height=500,
        hovermode='x unified',
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        plot_bgcolor=theme_colors['background_color'],
        paper_bgcolor=theme_colors['background_color'],
        font_color=theme_colors['text_color']
    )
    return fig

# ------------------------
# Sidebar Settings
# ------------------------
with st.sidebar:
    st.header("Settings")
    video_type = st.radio(
        "Video Type to Compare Against",
        options=["all", "long_form", "shorts", "auto"],
        format_func=lambda x: "All Videos" if x == "all" else (
            "Shorts Only" if x == "shorts" else (
                "Long-form Only" if x == "long_form" else "Auto-detect (match video type)"
            )
        ),
        index=3
    )
    comparison_approach = st.radio(
        "Comparison Approach",
        options=["Approach 1: Full Projection", 
                 "Approach 2: Compare by Video Age", 
                 "Approach 3: Compare by Video Age + Average"],
        index=0
    )
    if comparison_approach == "Approach 1: Full Projection":
        approach_mode = "full"
    elif comparison_approach == "Approach 2: Compare by Video Age":
        approach_mode = "current"
    else:
        approach_mode = "extra"
    max_days = st.slider(
        "Days to Analyze (for full projection)",
        min_value=7,
        max_value=3650,
        value=30,
        step=1,
        help="Number of days to analyze after video upload (set high for lifetime)"
    )
    include_all_videos = st.checkbox("Include all videos", value=False)
    if include_all_videos:
        num_videos = None
    else:
        num_videos = st.slider(
            "Number of videos to include",
            min_value=10,
            max_value=200,
            value=50,
            step=10,
            help="More videos creates a more stable benchmark"
        )
    percentile_range = st.slider(
        "Middle Percentage Range for Band",
        min_value=10,
        max_value=100,
        value=50,
        step=5,
        help="Middle percentage range for typical performance (e.g., 50 = 25th to 75th percentile, 80 = 10th to 90th percentile)"
    )
    show_data_tables = st.checkbox("Show data tables", value=False)

# ------------------------
# Main Input Section
# ------------------------
col1, col2 = st.columns(2)
with col1:
    channel_url = st.text_input("Channel URL:", placeholder="https://www.youtube.com/@ChannelName")
with col2:
    video_url = st.text_input("Video URL to Compare:", placeholder="https://www.youtube.com/watch?v=VideoID")

# ------------------------
# Main Process Flow
# ------------------------
if st.button("Generate Benchmark", type="primary") and channel_url and video_url:
    channel_id = extract_channel_id(channel_url)
    video_id = extract_video_id(video_url)
    if not channel_id:
        st.error("Could not extract a valid channel ID from the provided URL. Please check the URL format.")
        st.stop()
    if not video_id:
        st.error("Could not extract a valid video ID from the provided URL. Please check the URL format.")
        st.stop()
    with st.spinner("Fetching video details..."):
        video_details = fetch_single_video(video_id, yt_api_key)
        if not video_details:
            st.error("Failed to fetch video details. Please check the video URL.")
            st.stop()
        if video_details['channelId'] != channel_id:
            st.warning(f"The video belongs to channel '{video_details['channelTitle']}', which is different from the channel URL you provided. Analysis may not be accurate.")
        published_date = datetime.datetime.fromisoformat(video_details['publishedAt'].replace('Z', '+00:00')).date()
        video_age = (datetime.datetime.now().date() - published_date).days
        if approach_mode in ["current", "extra"]:
            analysis_days = video_age if video_age >= 2 else 2
        else:
            analysis_days = max_days
    with st.spinner("Fetching channel videos for benchmark..."):
        channel_videos, channel_name, channel_stats = fetch_channel_videos(channel_id, num_videos, yt_api_key)
        if not channel_videos:
            st.error("Failed to fetch channel videos. Please check the channel URL.")
            st.stop()
        st.markdown(f"<div class='success-box'>Channel: <b>{channel_name}</b> | Video: <b>{video_details['title']}</b></div>", unsafe_allow_html=True)
        col1, col2 = st.columns([1, 3])
        with col1:
            if video_details['thumbnailUrl']:
                st.image(video_details['thumbnailUrl'], width=200)
        with col2:
            minutes, seconds = divmod(video_details['duration'], 60)
            hours, minutes = divmod(minutes, 60)
            duration_str = f"{hours}h {minutes}m {seconds}s" if hours else f"{minutes}m {seconds}s"
            st.markdown(f"**Title:** {video_details['title']}")
            st.markdown(f"**Published:** {published_date} ({video_age} days ago)")
            st.markdown(f"**Duration:** {duration_str} ({'Short' if video_details['isShort'] else 'Long-form'})")
            metrics_cols = st.columns(3)
            with metrics_cols[0]:
                st.metric("Views", f"{video_details['viewCount']:,}")
            with metrics_cols[1]:
                st.metric("Likes", f"{video_details['likeCount']:,}")
            with metrics_cols[2]:
                st.metric("Comments", f"{video_details['commentCount']:,}")
    with st.spinner("Processing benchmark data..."):
        video_ids = [v['videoId'] for v in channel_videos]
        detailed_videos = fetch_video_details(video_ids, yt_api_key)
        # Remove the target video from the channel benchmark
        if video_id in detailed_videos:
            del detailed_videos[video_id]
        # Compute additional channel stats from benchmark videos
        vph_list = []
        engagement_list = []
        for vid, details in detailed_videos.items():
            if details['duration'] > 0:
                duration_hours = details['duration'] / 3600
                vph_list.append(details['viewCount'] / duration_hours)
            if details['viewCount'] > 0:
                engagement_list.append((details['likeCount'] + details['commentCount']) / details['viewCount'] * 100)
        avg_vph = np.mean(vph_list) if vph_list else 0
        avg_engagement = np.mean(engagement_list) if engagement_list else 0

        if video_type == "auto":
            is_short_filter = video_details['isShort']
            video_type_str = "Shorts" if is_short_filter else "Long-form Videos"
        elif video_type == "shorts":
            is_short_filter = True
            video_type_str = "Shorts"
        elif video_type == "long_form":
            is_short_filter = False
            video_type_str = "Long-form Videos"
        else:
            is_short_filter = None
            video_type_str = "All Videos"
        shorts_count = sum(1 for _, details in detailed_videos.items() if details['isShort'])
        longform_count = len(detailed_videos) - shorts_count
        if is_short_filter is True and shorts_count < 5:
            st.warning(f"Not enough Shorts in this channel (found {shorts_count}). Using all videos instead.")
            is_short_filter = None
            video_type_str = "All Videos"
        elif is_short_filter is False and longform_count < 5:
            st.warning(f"Not enough Long-form videos in this channel (found {longform_count}). Using all videos instead.")
            is_short_filter = None
            video_type_str = "All Videos"
        st.info(f"Building benchmark from {len(detailed_videos)} videos: {shorts_count} shorts and {longform_count} long-form videos")
        benchmark_df = generate_historical_data(detailed_videos, analysis_days, is_short_filter)
        if benchmark_df.empty:
            st.error("Not enough data to create a benchmark. Try including more videos or changing the video type filter.")
            st.stop()
        benchmark_stats = calculate_benchmark(benchmark_df, percentile_range)
        if approach_mode == "extra":
            benchmark_stats['avg_band'] = (benchmark_stats['lower_band'] + benchmark_stats['upper_band']) / 2
        sim_approach = "full" if approach_mode == "full" else "current"
        video_performance = simulate_video_performance(video_details, benchmark_stats, analysis_days, approach=sim_approach)
        fig = create_comparison_chart(benchmark_stats, video_performance, 
                                      video_details['title'][:40] + "..." if len(video_details['title']) > 40 else video_details['title'], 
                                      video_type_str, theme_colors, approach_mode=approach_mode)
        st.plotly_chart(fig, use_container_width=True)
        
        st.markdown("<div class='subheader'>Performance Analysis</div>", unsafe_allow_html=True)
        day_index = min(video_age, len(benchmark_stats) - 1)
        if day_index < 0:
            day_index = 0
        benchmark_median = benchmark_stats.loc[day_index, 'median']
        benchmark_lower = benchmark_stats.loc[day_index, 'lower_band']
        benchmark_upper = benchmark_stats.loc[day_index, 'upper_band']
        if approach_mode == "extra":
            benchmark_avg = (benchmark_lower + benchmark_upper) / 2
        if video_details['viewCount'] >= benchmark_upper:
            percentile = f"Top {100 - percentile_range}%"
            performance_color = "green"
        elif video_details['viewCount'] <= benchmark_lower:
            percentile = f"Bottom {percentile_range}%"
            performance_color = "red"
        else:
            range_width = benchmark_upper - benchmark_lower
            if range_width > 0:
                position_in_range = (video_details['viewCount'] - benchmark_lower) / range_width
                estimated_percentile = percentile_range + position_in_range * (100 - 2 * percentile_range)
                percentile = f"~{estimated_percentile:.0f}th percentile"
                performance_color = "orange"
            else:
                percentile = "Average"
                performance_color = "gray"
        if benchmark_median > 0:
            vs_benchmark_pct = ((video_details['viewCount'] / benchmark_median) - 1) * 100
            vs_benchmark_str = f"{vs_benchmark_pct:+.1f}% vs typical"
        else:
            vs_benchmark_str = "N/A"
        if approach_mode == "extra":
            metric_cols_extra = st.columns(5)
            with metric_cols_extra[0]:
                st.markdown(f"<div class='metric-card'><b>Current Views</b><br>{video_details['viewCount']:,}</div>", unsafe_allow_html=True)
            with metric_cols_extra[1]:
                st.markdown(f"<div class='metric-card'><b>Typical Views</b><br>{int(benchmark_median):,}</div>", unsafe_allow_html=True)
            with metric_cols_extra[2]:
                st.markdown(f"<div class='metric-card'><b>Channel Average</b><br>{int(benchmark_avg):,}</div>", unsafe_allow_html=True)
            with metric_cols_extra[3]:
                st.markdown(f"<div class='metric-card'><b>Performance</b><br><span style='color:{performance_color}'>{vs_benchmark_str}</span></div>", unsafe_allow_html=True)
            with metric_cols_extra[4]:
                st.markdown(f"<div class='metric-card'><b>Ranking</b><br><span style='color:{performance_color}'>{percentile}</span></div>", unsafe_allow_html=True)
            channel_stats_cols = st.columns(2)
            with channel_stats_cols[0]:
                st.metric("Channel VPH", f"{avg_vph:,.1f}")
            with channel_stats_cols[1]:
                st.metric("Channel Engagement Rate", f"{avg_engagement:,.1f}%")
        else:
            metric_cols = st.columns(4)
            with metric_cols[0]:
                st.markdown(f"<div class='metric-card'><b>Current Views</b><br>{video_details['viewCount']:,}</div>", unsafe_allow_html=True)
            with metric_cols[1]:
                st.markdown(f"<div class='metric-card'><b>Typical Views at this age</b><br>{int(benchmark_median):,}</div>", unsafe_allow_html=True)
            with metric_cols[2]:
                st.markdown(f"<div class='metric-card'><b>Performance</b><br><span style='color:{performance_color}'>{vs_benchmark_str}</span></div>", unsafe_allow_html=True)
            with metric_cols[3]:
                st.markdown(f"<div class='metric-card'><b>Ranking</b><br><span style='color:{performance_color}'>{percentile}</span></div>", unsafe_allow_html=True)
        if show_data_tables:
            st.markdown("<div class='subheader'>Data Tables</div>", unsafe_allow_html=True)
            tabs = st.tabs(["Benchmark Data", "Video Performance Data"])
            with tabs[0]:
                st.write("### Typical Performance Benchmark")
                st.dataframe(benchmark_stats)
            with tabs[1]:
                st.write("### Video Performance Data")
                st.dataframe(video_performance)
        st.markdown("<div class='subheader'>Download Data</div>", unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                "Download Benchmark Data", 
                benchmark_stats.to_csv(index=False), 
                f"{channel_name.replace(' ', '_')}_benchmark_{video_type_str.replace(' ', '_')}.csv",
                "text/csv",
                key='download-benchmark'
            )
        with col2:
            st.download_button(
                "Download Video Performance Data", 
                video_performance.to_csv(index=False),
                f"{video_id}_performance_data.csv",
                "text/csv",
                key='download-performance'
            )
