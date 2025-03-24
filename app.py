import streamlit as st
import requests
import pandas as pd
import numpy as np
import datetime
import plotly.graph_objects as go
from datetime import timedelta

# Page configuration
st.set_page_config(
    page_title="YouTube Analytics - Typical Performance",
    page_icon="📊",
    layout="wide"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {font-size: 2rem; font-weight: 600; margin-bottom: 1rem;}
    .subheader {font-size: 1.5rem; font-weight: 500; margin: 1rem 0;}
    .success-box {background-color: #dff0d8; padding: 1rem; border-radius: 5px; margin: 1rem 0;}
    .info-box {background-color: #d9edf7; padding: 1rem; border-radius: 5px; margin: 1rem 0;}
    .metric-card {background-color: #f8f9fa; padding: 1rem; border-radius: 5px; margin-bottom: 1rem;}
</style>
""", unsafe_allow_html=True)

# Main title
st.markdown("<div class='main-header'>YouTube Typical Performance (Gray Band) Data Fetcher</div>", unsafe_allow_html=True)
st.markdown("This tool fetches video data from a YouTube channel and generates a typical performance band visualization.")

# Sidebar for API configuration and advanced settings
with st.sidebar:
    st.header("⚙️ Configuration")
    
    # API Key input (with fallback to secrets)
    user_api_key = st.text_input("YouTube API Key (optional)", type="password", 
                                help="Leave blank to use key from secrets.toml")
    
    # Use API key from secrets if provided, otherwise use user input
    yt_api_key = st.secrets.get("YT_API_KEY") if not user_api_key else user_api_key
    
    if not yt_api_key:
        st.error("YouTube API Key is required - either add to secrets.toml or enter above")
    
    # Advanced settings
    st.subheader("Advanced Settings")
    use_real_data = st.checkbox("Use real YouTube data", value=False, 
                               help="If unchecked, will generate simulated data")
    
    show_raw_data = st.checkbox("Show raw data tables", value=False)
    use_median = st.checkbox("Use median for typical performance", value=True, 
                            help="If unchecked, will use mean")
    percentile_range = st.slider("Percentile Range for Gray Band", 10, 45, 25, 
                                help="Sets the width of the typical performance band (25 = 25th to 75th percentile)")

# Main input section
col1, col2, col3 = st.columns([3, 2, 2])

with col1:
    channel_id = st.text_input("Enter YouTube Channel ID:")
    
with col2:
    num_videos = st.number_input("Videos to include in gray band", 
                                 min_value=5, max_value=50, value=10,
                                 help="More videos means more stable typical performance")
    
with col3:
    days_to_analyze = st.number_input("Days of data to show", 
                                      min_value=7, max_value=90, value=17,
                                      help="Number of days to include in analysis")

# Function to fetch video data from YouTube
def fetch_youtube_data(channel_id, num_videos, api_key):
    # Step 1: Get Uploads Playlist ID
    playlist_url = f"https://www.googleapis.com/youtube/v3/channels?part=contentDetails,snippet&id={channel_id}&key={api_key}"
    try:
        playlist_res = requests.get(playlist_url).json()
        
        if 'items' not in playlist_res or not playlist_res['items']:
            st.error("Invalid Channel ID or no uploads found.")
            return None, None
            
        channel_name = playlist_res['items'][0]['snippet']['title']
        uploads_playlist_id = playlist_res['items'][0]['contentDetails']['relatedPlaylists']['uploads']
        
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
            
        return videos, channel_name
        
    except Exception as e:
        st.error(f"Error fetching YouTube data: {e}")
        return None, None

# Function to generate simulated view data
def generate_simulated_data(videos, days_to_analyze):
    data = []
    today = datetime.datetime.now().date()
    
    # Different performance patterns
    patterns = [
        # High performer
        lambda day: 20000 * np.sqrt(day + 1) + np.random.normal(0, 5000),
        # Medium performer with quick start
        lambda day: 15000 * np.log(day + 2) + np.random.normal(0, 3000),
        # Medium performer with slow start
        lambda day: 5000 * day**0.8 + np.random.normal(0, 2000),
        # Low performer
        lambda day: 3000 * np.log(day + 2) + np.random.normal(0, 1000)
    ]
    
    for video in videos:
        # Assign a random pattern to each video
        pattern_idx = np.random.randint(0, len(patterns))
        pattern = patterns[pattern_idx]
        
        cumulative_views = 0
        
        for day in range(days_to_analyze + 1):
            # Calculate daily views
            if day == 0:
                daily_views = np.random.randint(5000, 15000)
            else:
                daily_views = max(500, int(pattern(day) - cumulative_views))
            
            cumulative_views += daily_views
            
            # Create a date for this day relative to video publish date
            try:
                if 'publishedAt' in video and video['publishedAt']:
                    publish_date = datetime.datetime.fromisoformat(video['publishedAt'].replace('Z', '+00:00')).date()
                    date = publish_date + timedelta(days=day)
                else:
                    # Fallback if no publish date
                    date = today - timedelta(days=(days_to_analyze - day))
            except:
                # Another fallback
                date = today - timedelta(days=(days_to_analyze - day))
            
            data.append({
                "videoId": video['videoId'],
                "title": video.get('title', f"Video {video['videoId']}"),
                "day": day,
                "date": date,
                "daily_views": daily_views,
                "cumulative_views": cumulative_views
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
def create_performance_chart(df, summary, selected_video_id=None):
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
        fillcolor='rgba(200, 200, 200, 0.5)',
        line=dict(width=0),
        mode='lines'
    ))
    
    # Add the typical performance line
    fig.add_trace(go.Scatter(
        x=summary['day'], 
        y=summary['typical'],
        name='Typical Performance',
        line=dict(color='rgba(100, 100, 100, 0.8)', width=2, dash='dash'),
        mode='lines'
    ))
    
    # Add specific video if selected
    if selected_video_id:
        video_data = df[df['videoId'] == selected_video_id]
        if not video_data.empty:
            fig.add_trace(go.Scatter(
                x=video_data['day'], 
                y=video_data['cumulative_views'],
                name=video_data['title'].iloc[0][:30] + '...' if len(video_data['title'].iloc[0]) > 30 else video_data['title'].iloc[0],
                line=dict(color='red', width=3),
                mode='lines'
            ))
    
    # Layout updates
    fig.update_layout(
        title='Video Performance Over Time',
        xaxis_title='Days Since Upload',
        yaxis_title='Cumulative Views',
        height=600,
        hovermode='x unified',
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )
    
    return fig

# Main process flow
if st.button("Fetch Data", type="primary") and channel_id:
    with st.spinner("Fetching channel data..."):
        if yt_api_key:
            videos, channel_name = fetch_youtube_data(channel_id, num_videos, yt_api_key)
            
            if not videos:
                st.error("Failed to fetch video data. Please check your channel ID and API key.")
                st.stop()
                
            st.markdown(f"<div class='success-box'>Successfully fetched data for channel: <b>{channel_name}</b></div>", unsafe_allow_html=True)
            
            # Generate or fetch view data
            if not use_real_data:
                with st.spinner("Generating simulated view data..."):
                    df = generate_simulated_data(videos, days_to_analyze)
                    st.info("Using simulated data. For real view data, YouTube API requires OAuth integration.")
            else:
                # In a real application, you'd need to use YouTube Analytics API with OAuth
                # This would require a more complex authentication flow
                st.warning("Real YouTube Analytics data requires OAuth integration which is beyond this demo's scope.")
                df = generate_simulated_data(videos, days_to_analyze)
            
            # Calculate typical performance band
            summary = calculate_gray_band(df, percentile_range, use_median)
            
            # Display video selection dropdown
            st.markdown("<div class='subheader'>Select a video to compare to typical performance</div>", unsafe_allow_html=True)
            
            # Group videos by ID and get titles
            video_options = df[['videoId', 'title']].drop_duplicates().set_index('videoId')['title'].to_dict()
            selected_video = st.selectbox("Choose a video", 
                                         options=list(video_options.keys()),
                                         format_func=lambda x: video_options[x])
            
            # Display the chart
            fig = create_performance_chart(df, summary, selected_video)
            st.plotly_chart(fig, use_container_width=True)
            
            # Show key metrics for selected video
            if selected_video:
                video_data = df[df['videoId'] == selected_video].sort_values('day')
                
                if not video_data.empty:
                    latest_data = video_data.iloc[-1]
                    typical_at_same_day = summary[summary['day'] == latest_data['day']]
                    
                    if not typical_at_same_day.empty:
                        typical_views = typical_at_same_day['typical'].values[0]
                        performance_vs_typical = (latest_data['cumulative_views'] / typical_views - 1) * 100
                        
                        metric_cols = st.columns(4)
                        with metric_cols[0]:
                            st.markdown(f"<div class='metric-card'><b>Current Views</b><br>{int(latest_data['cumulative_views']):,}</div>", unsafe_allow_html=True)
                        with metric_cols[1]:
                            st.markdown(f"<div class='metric-card'><b>Days Live</b><br>{int(latest_data['day'])}</div>", unsafe_allow_html=True)
                        with metric_cols[2]:
                            st.markdown(f"<div class='metric-card'><b>Typical Views at this age</b><br>{int(typical_views):,}</div>", unsafe_allow_html=True)
                        with metric_cols[3]:
                            st.markdown(f"<div class='metric-card'><b>Performance vs Typical</b><br>{performance_vs_typical:.1f}%</div>", unsafe_allow_html=True)
            
            # Display the data tables if requested
            if show_raw_data:
                st.markdown("<div class='subheader'>Data Tables</div>", unsafe_allow_html=True)
                
                tabs = st.tabs(["Gray Band Data", "Video Data", "Raw Data"])
                
                with tabs[0]:
                    st.write("### Typical Performance (Gray Band) Data")
                    st.dataframe(summary)
                    
                with tabs[1]:
                    st.write("### Selected Video Data")
                    if selected_video:
                        st.dataframe(df[df['videoId'] == selected_video].sort_values('day'))
                        
                with tabs[2]:
                    st.write("### All Raw Data")
                    st.dataframe(df)
            
            # Download options
            st.markdown("<div class='subheader'>Download Data</div>", unsafe_allow_html=True)
            col1, col2 = st.columns(2)
            
            with col1:
                st.download_button(
                    "Download Gray Band Data", 
                    summary.to_csv(index=False), 
                    "youtube_gray_band.csv",
                    "text/csv",
                    key='download-gray-band'
                )
                
            with col2:
                st.download_button(
                    "Download All Video Data", 
                    df.to_csv(index=False),
                    "youtube_video_data.csv",
                    "text/csv",
                    key='download-all-data'
                )
        else:
            st.error("YouTube API Key is required. Please add to secrets.toml or enter in the sidebar.")

# Display instructions at the bottom
with st.expander("💡 How to use this tool"):
    st.markdown("""
    1. **Enter a YouTube Channel ID** - This is the unique identifier for a YouTube channel (not the channel name)
    2. **Choose how many videos** to include in the gray band calculation (more videos = more stable band)
    3. **Click 'Fetch Data'** to retrieve and analyze the data
    4. Select a specific video from the dropdown to compare it to the typical performance band
    5. Download the data in CSV format for further analysis
    
    **Note:** For actual YouTube Analytics data, you would need OAuth integration which is beyond the scope of this demo. This tool currently uses simulated data based on realistic patterns.
    """)
