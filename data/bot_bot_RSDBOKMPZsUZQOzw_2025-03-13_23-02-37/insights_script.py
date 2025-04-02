import json
import re

def load_json(filename):
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)

def extract_emotion_frames_from_raw(raw):
    """
    Extracts face prediction frames from the raw_result string.
    Each frame is expected to include a 'time' value and a list of EmotionScore entries.
    
    For example, a segment might look like:
    FacePrediction(frame=0, time=0.0, ..., emotions=[EmotionScore(name='Admiration', score=0.09346), ...])
    
    This function returns a list of dictionaries with keys:
      - "time": a float (in seconds)
      - "emotions": a list of dictionaries with keys "name" and "score"
    """
    # Improved pattern to capture FacePrediction blocks with time and emotions
    pattern = r"FacePrediction\(frame=\d+,\s*time=([0-9.]+).*?emotions=\[(.*?)\]"
    matches = re.findall(pattern, raw, re.DOTALL)
    
    frames = []
    for time_str, emotions_str in matches:
        try:
            time_val = float(time_str)
        except ValueError:
            continue

        # Pattern to capture individual emotion entries
        emotion_pattern = r"EmotionScore\(name=['\"]([^'\"]+)['\"],\s*score=([0-9.]+)"
        emotion_matches = re.findall(emotion_pattern, emotions_str)
        
        emotions = []
        for name, score_str in emotion_matches:
            try:
                score_val = float(score_str)
            except ValueError:
                score_val = 0.0
            emotions.append({"name": name, "score": score_val})
        
        if emotions:  # Only add frames that have emotion data
            frames.append({"time": time_val, "emotions": emotions})
    
    print(f"Extracted {len(frames)} frames with emotion data")
    return frames

def extract_emotion_frames(hume_data):
    """
    Extract emotion frames from the Hume analysis data.
    The data is expected to be in a nested structure with a 'raw_result' field
    that contains a string representation of Python objects.
    """
    # First check if the raw_result is directly in hume_data
    raw = hume_data.get("raw_result", "")
    
    # If not, check if it's nested under 'result'
    if not raw and "result" in hume_data:
        raw = hume_data.get("result", {}).get("raw_result", "")
    
    if not raw:
        print("No raw_result field found in Hume data.")
        return []
    
    frames = extract_emotion_frames_from_raw(raw)
    return frames

def average_emotions_for_segment(frames, start_time, end_time):
    # Filter frames that fall within the provided time window
    selected = [frame for frame in frames if start_time <= frame.get("time", 0) <= end_time]
    if not selected:
        return {}
    
    emotion_totals = {}
    count = 0
    for frame in selected:
        for emotion in frame.get("emotions", []):
            name = emotion.get("name")
            score = emotion.get("score", 0)
            emotion_totals[name] = emotion_totals.get(name, 0) + score
        count += 1
    
    avg_emotions = {name: total / count for name, total in emotion_totals.items()}
    return avg_emotions

def main():
    # Load the JSON files
    try:
        hume_data = load_json("hume_analysis.json")
        print("Successfully loaded hume_analysis.json")
    except Exception as e:
        print(f"Error loading hume_analysis.json: {e}")
        hume_data = {}
    
    try:
        transcript_data = load_json("transcript_raw.json")
        print("Successfully loaded transcript_raw.json")
    except Exception as e:
        print(f"Error loading transcript_raw.json: {e}")
        transcript_data = []
    
    # Extract emotion frames from the Hume analysis data
    frames = extract_emotion_frames(hume_data)
    if not frames:
        print("No emotion frames extracted.")
    
    # Determine a baseline timestamp from the transcript data (in seconds)
    if transcript_data:
        baseline = min(segment.get("timestamp_ms", 0) for segment in transcript_data) / 1000.0
    else:
        baseline = 0

    insights = []
    for segment in transcript_data:
        # Convert transcript timestamps from milliseconds to seconds and make them relative to the baseline
        seg_start = (segment.get("timestamp_ms", 0) / 1000.0) - baseline
        seg_duration = segment.get("duration_ms", 0) / 1000.0
        seg_end = seg_start + seg_duration
        
        # Compute average emotion scores for frames within the segment window
        avg_emotions = average_emotions_for_segment(frames, seg_start, seg_end)
        insights.append({
            "transcript": segment.get("transcription", {}).get("transcript", ""),
            "start": seg_start,
            "end": seg_end,
            "avg_emotions": avg_emotions
        })
    
    # Print the insights for each transcript segment
    for insight in insights:
        print(f"Segment from {insight['start']:.2f} to {insight['end']:.2f} seconds:")
        print("Transcript:")
        print(insight["transcript"])
        print("Average Emotion Scores:")
        if insight["avg_emotions"]:
            # Sort emotions by score (highest first) and show top 5
            top_emotions = sorted(insight["avg_emotions"].items(), key=lambda x: x[1], reverse=True)[:5]
            for emotion, score in top_emotions:
                print(f"  {emotion}: {score:.2f}")
        else:
            print("  No emotion data available for this segment.")
        print("\n" + "-"*50 + "\n")

    # Save insights to a JSON file
    try:
        with open("insights.json", "w", encoding="utf-8") as f:
            json.dump(insights, f, indent=2)
        print("Insights saved to insights.json")
    except Exception as e:
        print(f"Error saving insights to file: {e}")

if __name__ == "__main__":
    main()
