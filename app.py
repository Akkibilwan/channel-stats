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
    page_title="YouTube Analytics - Typical Performance",
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
    line_color = "#BB86FC"
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
    line_color = "#6200EE"

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
st.markdown(f"<div class='main-header'>YouTube Channel Typical Performance Analysis</div>", unsafe_allow_html=True)
st.markdown("Visualize how videos typically perform over their lifetime, showing the day-by-day view growth pattern.")

# Safely load API key from secrets.toml
try:
    yt_api_key = st.secrets["YT_API_KEY"]
    if not yt_api_key:
        st.error("YouTube API Key is missing from secrets.toml!")
        st.stop()
except Exception as e:
    st.error(f"Error loading API key from secrets: {e}. Please check your secrets.toml file.")
    st.stop()

# Function to extract channel ID from channel URL
def extract_channel_id(url):
    # Patterns for different YouTube channel URL formats
    patterns = [
        r'youtube\.com/channel/([^/\s]+)',     # Standard channel URL
        r'youtube\.com/c/([^/\s]+)',           # Custom URL
        r'youtube\.com/user/([^/\s]+)',        # Legacy username URL
        r'youtube\.com/@([^/\s]+)'             # Handle URL (@username)
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            identifier = match.group(1)
            
            # If it's a direct channel ID (starts with UC), return it
            if pattern == patterns[0] and identifier.startswith('UC'):
                return identifier
            
            # For custom URLs, usernames, or handles, we need to make an API call
            return get_channel_id_from_identifier(identifier, pattern)
    
    # If no pattern matches, try treating the input as a direct channel ID
    if url.strip().startswith('UC'):
        return url.strip()
        
    return None

# Function to get channel ID from custom URL, username, or handle
def get_channel_id_from_identifier(identifier, pattern_used):
    try:
        # For standard channel URLs with UC format
        if pattern_used == r'youtube\.com/channel/([^/\s]+)':
            return identifier
        
        # For custom URLs (youtube.com/c/name)
        elif pattern_used == r'youtube\.com/c/([^/\s]+)':
            # Need to use search API since there's no direct endpoint for custom URLs
            search_url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&type=channel&q={identifier}&key={yt_api_key}"
            
        # For legacy username URLs (youtube.com/user/name)
        elif pattern_used == r'youtube\.com/user/([^/\s]+)':
            username_url = f"https://www.googleapis.com/youtube/v3/channels?part=id&forUsername={identifier}&key={yt_api_key}"
            username_res = requests.get(username_url).json()
            if 'items' in username_res and username_res['items']:
                return username_res['items'][0]['id']
            
            # Fallback to search if no direct match
            search_url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&type=channel&q={identifier}&key={yt_api_key}"
        
        # For handle URLs (youtube.com/@name)
        elif pattern_used == r'youtube\.com/@([^/\s]+)':
            # Remove @ if present in the identifier
            if identifier.startswith('@'):
                identifier = identifier[1:]
            # Need to use search API since there's no direct endpoint for handles
            search_url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&type=channel&q={identifier}&key={yt_api_key}"
        
        # For any other pattern, use search
        else:
            search_url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&type=channel&q={identifier}&key={yt_api_key}"
        
        # Execute search if needed
        if 'search_url' in locals():
            search_res = requests.get(search_url).json()
            if 'items' in search_res and search_res['items']:
                return search_res['items'][0]['id']['channelId']
        
    except Exception as e:
        st.error(f"Error resolving channel identifier: {e}")
    
    return None

# Function to fetch video data from YouTube
def fetch_youtube_data(channel_id, num_videos, api_key):
    # Step 1: Get Uploads Playlist ID
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
        
        # Step 2: Get video IDs from uploads playlist
        videos = []
        next_page_token = ""
        
        while len(videos) < num_videos and next_page_token is not None:
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
                
                if len(videos) >= num_videos:
                    break
                    
            next_page_token = playlist_items_res.get('nextPageToken')
            
        return videos, channel_name, channel_stats
        
    except Exception as e:
        st.error(f"Error fetching YouTube data: {e}")
        return None, None, None

# Function to fetch video details including duration
def fetch_video_details(video_ids, api_key):
    if not video_ids:
        return {}
    
    # Can only fetch 50 videos at a time, so chunk if needed
    all_details = {}
    video_chunks = [video_ids[i:i+50] for i in range(0, len(video_ids), 50)]
    
    for chunk in video_chunks:
        video_ids_str = ','.join(chunk)
        details_url = f"https://www.googleapis.com/youtube/v3/videos?part=contentDetails,statistics&id={video_ids_str}&key={api_key}"
        
        try:
            details_res = requests.get(details_url).json()
            for item in details_res.get('items', []):
                # Extract duration in seconds
                duration_str = item['contentDetails']['duration']  # PT1M30S format
                duration_seconds = parse_duration(duration_str)
                
                all_details[item['id']] = {
                    'duration': duration_seconds,
                    'viewCount': int(item['statistics'].get('viewCount', 0)),
                    'isShort': duration_seconds <= 120  # Consider videos ≤ 120 seconds as shorts
                }
        except Exception as e:
            st.warning(f"Error fetching details for some videos: {e}")
    
    return all_details

# Function to parse ISO 8601 duration format to seconds
def parse_duration(duration_str):
    # PT1H30M15S format - hours, minutes, seconds
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

# Function to generate simulated view data
def generate_simulated_data(videos, video_details, max_days):
    data = []
    today = datetime.datetime.now().date()
    
    # Different performance patterns for regular videos and shorts
    regular_patterns = [
        # High performer
        lambda day: 10000 * np.sqrt(day + 1) + np.random.normal(0, 2000),
        # Medium performer with quick start
        lambda day: 7500 * np.log(day + 2) + np.random.normal(0, 1500),
        # Medium performer with slow start
        lambda day: 2500 * day**0.8 + np.random.normal(0, 1000),
        # Low performer
        lambda day: 1500 * np.log(day + 2) + np.random.normal(0, 500)
    ]
    
    shorts_patterns = [
        # Viral short
        lambda day: 50000 * np.sqrt(day + 1) * np.exp(-day/10) + np.random.normal(0, 10000),
        # Good performing short
        lambda day: 30000 * np.sqrt(day + 1) * np.exp(-day/7) + np.random.normal(0, 5000),
        # Average short
        lambda day: 15000 * np.sqrt(day + 1) * np.exp(-day/5) + np.random.normal(0, 3000),
        # Poor performing short
        lambda day: 5000 * np.sqrt(day + 1) * np.exp(-day/3) + np.random.normal(0, 1000)
    ]
    
    for video in videos:
        video_id = video['videoId']
        
        # Skip if video details not available
        if video_id not in video_details:
            continue
            
        # Select pattern based on video type
        is_short = video_details[video_id]['isShort']
        real_views = video_details[video_id]['viewCount']
        
        if is_short:
            pattern_idx = np.random.randint(0, len(shorts_patterns))
            pattern = shorts_patterns[pattern_idx]
        else:
            pattern_idx = np.random.randint(0, len(regular_patterns))
            pattern = regular_patterns[pattern_idx]
        
        # Calculate publish date and video age
        publish_date = None
        try:
            if 'publishedAt' in video and video['publishedAt']:
                publish_date = datetime.datetime.fromisoformat(video['publishedAt'].replace('Z', '+00:00')).date()
                video_age_days = (today - publish_date).days
            else:
                video_age_days = np.random.randint(max_days, max_days * 2)  # Random age if no publish date
                publish_date = today - timedelta(days=video_age_days)
        except:
            video_age_days = np.random.randint(max_days, max_days * 2)  # Fallback
            publish_date = today - timedelta(days=video_age_days)
        
        # Only simulate up to actual video age or max_days, whichever is less
        days_to_simulate = min(video_age_days, max_days)
        
        cumulative_views = 0
        daily_views_list = []
        
        # Generate daily views
        for day in range(days_to_simulate + 1):
            if day == 0:
                daily_views = np.random.randint(1000, 5000) if not is_short else np.random.randint(5000, 20000)
            else:
                target_cumulative = pattern(day)
                daily_views = max(100, int(target_cumulative - cumulative_views))
            
            daily_views_list.append(daily_views)
            cumulative_views += daily_views
        
        # Scale simulated views to match actual current views
        if cumulative_views > 0 and real_views > 0:
            scale_factor = real_views / cumulative_views
            daily_views_list = [int(v * scale_factor) for v in daily_views_list]
            
            # Recalculate cumulative views with scaled daily views
            cum_views = 0
            for day, daily_views in enumerate(daily_views_list):
                cum_views += daily_views
                
                data.append({
                    "videoId": video_id,
                    "title": video.get('title', f"Video {video_id}"),
                    "isShort": is_short,
                    "day": day,
                    "date": publish_date + timedelta(days=day) if publish_date else None,
                    "daily_views": daily_views,
                    "cumulative_views": cum_views
                })
    
    return pd.DataFrame(data)

# Function to calculate the gray band data
def calculate_gray_band(df, percentile_range, use_median=True):
    central = 'median' if use_median else 'mean'
    
    summary = df.groupby('day')['cumulative_views'].agg([
        ('lower_band', lambda x: x.quantile(percentile_range/100)),
        ('upper_band', lambda x: x.quantile(1 - percentile_range/100)),
        ('typical', central)
    ]).reset_index()
    
    return summary

# Function to create the visualization
def create_performance_chart(summary, max_days, video_type, theme_colors):
    fig = go.Figure()
    
    # Add the gray band (typical performance)
    fig.add_trace(go.Scatter(
        x=summary['day'], 
        y=summary['upper_band'],
        name='Upper Bound',
        mode='lines',
        line=dict(width=0),
        showlegend=False
    ))
    
    fig.add_trace(go.Scatter(
        x=summary['day'], 
        y=summary['lower_band'],
        name='Typical Performance Range',
        fill='tonexty',
        fillcolor=theme_colors['gray_band_color'],
        line=dict(width=0),
        mode='lines'
    ))
    
    # Add the typical performance line
    fig.add_trace(go.Scatter(
        x=summary['day'], 
        y=summary['typical'],
        name='Typical Performance',
        line=dict(color=theme_colors['line_color'], width=3),
        mode='lines'
    ))
    
    # Determine title based on video type selection
    if video_type == "all":
        title = "Typical Performance: All Videos"
    elif video_type == "shorts":
        title = "Typical Performance: Shorts Only"
    else:
        title = "Typical Performance: Long-form Videos Only"
    
    # Layout updates
    fig.update_layout(
        title=title,
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

# Sidebar settings
with st.sidebar:
    st.header("Settings")
    
    # Video type filter
    video_type = st.radio(
        "Video Type",
        options=["all", "long_form", "shorts"],
        format_func=lambda x: "All Videos" if x == "all" else ("Shorts Only" if x == "shorts" else "Long-form Only")
    )
    
    # Time range options
    time_range = st.selectbox(
        "Analysis Timeframe",
        options=["30", "60", "90", "365", "max"],
        format_func=lambda x: f"{x} days" if x != "max" else "Lifetime",
        index=0
    )
    
    # Convert timeframe to integer days
    if time_range == "max":
        max_days = 1000  # Some large number for "lifetime"
    else:
        max_days = int(time_range)
    
    # Number of videos to analyze
    num_videos = st.slider(
        "Videos to include in analysis",
        min_value=10,
        max_value=200,
        value=50,
        step=10,
        help="More videos means more stable typical performance band"
    )
    
    # Band percentile range
    percentile_range = st.slider(
        "Percentile Range for Band",
        min_value=10,
        max_value=45,
        value=25,
        step=5,
        help="Width of the typical performance band (25 = 25th to 75th percentile)"
    )
    
    # Use median or mean
    use_median = st.checkbox(
        "Use median (uncheck for mean)",
        value=True,
        help="Median is less affected by outliers"
    )

# Main input section
channel_url = st.text_input("Enter YouTube Channel URL:", placeholder="https://www.youtube.com/@ChannelName")

# Main process flow
if st.button("Analyze Channel", type="primary") and channel_url:
    # Extract channel ID from URL
    channel_id = extract_channel_id(channel_url)
    
    if not channel_id:
        st.error("Could not extract a valid channel ID from the provided URL. Please check the URL format.")
        st.stop()
    
    with st.spinner("Fetching channel data..."):
        videos, channel_name, channel_stats = fetch_youtube_data(channel_id, num_videos, yt_api_key)
        
        if not videos:
            st.error("Failed to fetch video data. Please check the channel URL.")
            st.stop()
            
        st.markdown(f"<div class='success-box'>Channel: <b>{channel_name}</b></div>", unsafe_allow_html=True)
        
        # Display channel stats
        total_subs = int(channel_stats.get('subscriberCount', 0))
        total_views = int(channel_stats.get('viewCount', 0))
        total_videos = int(channel_stats.get('videoCount', 0))
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"<div class='metric-card'><b>Subscribers</b><br>{total_subs:,}</div>", unsafe_allow_html=True)
        with col2:
            st.markdown(f"<div class='metric-card'><b>Total Views</b><br>{total_views:,}</div>", unsafe_allow_html=True)
        with col3:
            st.markdown(f"<div class='metric-card'><b>Videos</b><br>{total_videos:,}</div>", unsafe_allow_html=True)
        
        # Fetch video details including duration for shorts classification
        with st.spinner("Fetching video details..."):
            video_ids = [v['videoId'] for v in videos]
            video_details = fetch_video_details(video_ids, yt_api_key)
            
            # Count shorts vs. long-form videos
            shorts_count = sum(1 for _, details in video_details.items() if details['isShort'])
            longform_count = len(video_details) - shorts_count
            
            if video_type == "shorts" and shorts_count == 0:
                st.warning(f"No shorts found in the analyzed videos. Showing all videos instead.")
                video_type = "all"
            elif video_type == "long_form" and longform_count == 0:
                st.warning(f"No long-form videos found in the analyzed videos. Showing all videos instead.")
                video_type = "all"
                
            st.info(f"Analyzed {len(video_details)} videos: {shorts_count} shorts and {longform_count} long-form videos")
        
        # Generate view data
        with st.spinner("Generating view data..."):
            all_data = generate_simulated_data(videos, video_details, max_days)
            
            # Filter based on video type selection
            if video_type == "shorts":
                filtered_data = all_data[all_data['isShort'] == True]
            elif video_type == "long_form":
                filtered_data = all_data[all_data['isShort'] == False]
            else:  # "all"
                filtered_data = all_data
            
            if filtered_data.empty:
                st.error(f"No data available for the selected video type filter.")
                st.stop()
        
        # Calculate typical performance band
        summary = calculate_gray_band(filtered_data, percentile_range, use_median)
        
        # Select only days up to max_days
        summary = summary[summary['day'] <= max_days]
        
        # Theme colors for the chart
        theme_colors = {
            'background_color': background_color,
            'text_color': text_color,
            'line_color': line_color,
            'gray_band_color': gray_band_color
        }
        
        # Display the chart
        fig = create_performance_chart(summary, max_days, video_type, theme_colors)
        st.plotly_chart(fig, use_container_width=True)
        
        # Download options
        st.markdown("<div class='subheader'>Download Data</div>", unsafe_allow_html=True)
        
        st.download_button(
            "Download Typical Performance Data (CSV)", 
            summary.to_csv(index=False), 
            f"{channel_name.replace(' ', '_')}_typical_performance_{video_type}_{time_range}days.csv",
            "text/csv",
            key='download-data'
        )
