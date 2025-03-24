import streamlit as st
import requests
import pandas as pd
import datetime

# Safely load API key
yt_api_key = st.secrets.get("YT_API_KEY", None)

if not yt_api_key:
    st.error("YouTube API Key is missing from secrets.toml!")
    st.stop()

# Streamlit UI
st.title("YouTube Typical Performance (Gray Band) Data Fetcher")

channel_id = st.text_input("Enter Channel ID:")
num_videos = st.number_input("Number of past videos to include in gray band (recommend 10-30)", min_value=5, max_value=50, value=10)

if st.button("Fetch Data") and channel_id:
    # Step 1: Get Uploads Playlist ID
    playlist_url = f"https://www.googleapis.com/youtube/v3/channels?part=contentDetails&id={channel_id}&key={yt_api_key}"
    playlist_res = requests.get(playlist_url).json()

    if 'items' not in playlist_res or not playlist_res['items']:
        st.error("Invalid Channel ID or no uploads found.")
        st.stop()

    uploads_playlist_id = playlist_res['items'][0]['contentDetails']['relatedPlaylists']['uploads']

    # Step 2: Get video IDs from uploads playlist
    videos = []
    next_page_token = ""

    while len(videos) < num_videos and next_page_token is not None:
        playlist_items_url = f"https://www.googleapis.com/youtube/v3/playlistItems?part=contentDetails&maxResults=10&playlistId={uploads_playlist_id}&key={yt_api_key}"
        if next_page_token:
            playlist_items_url += f"&pageToken={next_page_token}"

        playlist_items_res = requests.get(playlist_items_url).json()

        for item in playlist_items_res.get('items', []):
            videos.append(item['contentDetails']['videoId'])
            if len(videos) >= num_videos:
                break

        next_page_token = playlist_items_res.get('nextPageToken')

    st.success(f"Fetched {len(videos)} video IDs")

    # Step 3: Build the gray band data
    data = []
    for video_id in videos:
        # Placeholder - Simulate daily views for demonstration
        for day in range(0, 18):
            data.append({
                "videoId": video_id,
                "day": day,
                "views": day * 100 + hash(video_id) % 500  # Fake data
            })

    df = pd.DataFrame(data)

    # Step 4: Calculate percentiles for gray band
    summary = df.groupby('day')['views'].agg([
        ('Q1 (25%)', lambda x: x.quantile(0.25)),
        ('Median', 'median'),
        ('Q3 (75%)', lambda x: x.quantile(0.75))
    ]).reset_index()

    st.write("### Gray Band Data (Percentiles)")
    st.dataframe(summary)

    # Optional: Save to CSV
    st.download_button("Download CSV", summary.to_csv(index=False), "gray_band.csv")

st.caption("Note: To fully automate with YouTube Analytics API, OAuth authentication would be required.")
