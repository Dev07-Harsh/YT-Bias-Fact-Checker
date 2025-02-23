from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import requests
from youtube_transcript_api import YouTubeTranscriptApi
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

app = Flask(__name__)
CORS(app)


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CX = os.getenv("GOOGLE_CX")


genai.configure(api_key=GEMINI_API_KEY)


generation_config_eval = {
    "temperature": 0.7,
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 1000,  
}

generation_config_query = {
    "temperature": 0.3,
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 100, 
}

def get_transcript_any_language(video_id):
    """
    Attempts to fetch an English transcript first.
    If not available, iterates over the list of available transcripts
    and returns the first transcript that can be fetched.
    """
    try:
       
        return YouTubeTranscriptApi.get_transcript(video_id, languages=['en'])
    except Exception as e:
        # DEBUG: print("English transcript not found, trying available transcripts. Error:", e)
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        for transcript in transcript_list:
            try:
                return transcript.fetch()
            except Exception as e:
                # DEBUG: print("Failed to fetch transcript in", transcript.language, "Error:", e)
                pass
        raise Exception("Could not retrieve any transcript for video: " + video_id)

def generate_text(prompt, generation_config):
    """
    Uses the google.generativeai library to generate text using the Gemini model.
    """
    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash-exp",
        generation_config=generation_config,
    )
    chat_session = model.start_chat(history=[])
    response = chat_session.send_message(prompt)
    return response.text.strip()

def perform_google_search(query):
    url = f"https://www.googleapis.com/customsearch/v1?key={GOOGLE_API_KEY}&cx={GOOGLE_CX}&q={requests.utils.quote(query)}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        items = data.get("items", [])
        if items:
            sources = []
            for item in items:
                title = item.get("title", "")
                link = item.get("link", "")
                snippet = item.get("snippet", "")
                sources.append(f"{title}: {link} - {snippet}")
            return sources
        else:
            return ["No reliable sources found"]
    else:
        print("Error fetching search results:", response.text)  # Debug log
        return ["Error fetching search results"]


@app.route("/evaluate", methods=["POST"])
def evaluate():
    data = request.get_json()
    video_id = data.get("videoId")
    if not video_id:
        return jsonify({"error": "videoId is required"}), 400

    try:
       
        transcript_entries = get_transcript_any_language(video_id)
        transcript = " ".join([entry["text"] for entry in transcript_entries])
       

        # ---Search Query Generation Prompt with Length Limitation ---
        prompt_for_query = f"""
You are a search query expert specializing in crafting concise and effective search queries from lengthy transcripts. Analyze the transcript provided below and extract a brief, fact-based search query that captures all relevant factual points from the video. Please ensure that the query:
- Clearly identifies the primary subject and key themes discussed in the transcript.
- Includes essential factual details, such as names, dates, events, and significant terms.
- Excludes any promotional content, advertisements, or irrelevant information.
- Is structured to maximize retrieval of high-quality and reliable factual information from reputable sources.
- Uses specific keywords or phrases that reflect the core message of the video.
- Is limited to no more than 20-30 words for optimal search performance.

Transcript:
{transcript}
"""
        search_query = generate_text(prompt_for_query, generation_config_query)
        print("Generated Search Query:", search_query)

        # Retrieve reliable sources using the Google Custom Search API
        reliable_sources = perform_google_search(search_query)
        # DEBUG: print("Reliable Sources:", reliable_sources)
        print("Data received after web search:", reliable_sources)
        
        reliable_sources_str = "\n".join(reliable_sources)

        # --- Refined Evaluation Prompt with Length Limitation ---
        prompt_evaluation = f"""
You are an expert fact-checker and media analyst with extensive experience in evaluating online video content for accuracy, bias, and logical consistency. Given the following transcript from a YouTube video and a list of reliable sources with factual data, please perform a comprehensive analysis using the steps below. Note: Ignore any promotions, advertisements, or monetization content as these are not relevant to factual accuracy or bias.

1. **Key Factual Points:**  
   - Identify and list the main factual assertions and claims made in the transcript.
   
2. **Source Verification:**  
   - For each factual point, compare it with the information provided by the reliable sources.
   - Highlight any discrepancies, confirmations, or additional context provided by the sources.
   
3. **Bias and Representation Analysis:**  
   - Examine the transcript for any signs of bias, including selective presentation of facts, omission of alternative viewpoints, or use of emotionally charged language.
   - Note if certain perspectives are overemphasized or ignored.
   
4. **Logical Consistency and Reasoning:**  
   - Assess the logical flow of the arguments in the transcript.
   - Identify any logical fallacies, inconsistencies, or gaps in the reasoning.
   
5. **Additional Observations:**  
   - Note any misleading statements or rhetorical strategies that could influence the audience's perception.
   
6. **Overall Assessment:**  
   - Provide a concise summary judgment on the overall credibility, balance, and reliability of the video's content.

Please produce your evaluation in a clear, structured bullet-point format, and ensure that in any case the final output does not exceed 500 words.

Transcript:
{transcript}

Reliable Sources:
{reliable_sources_str}
"""
        evaluation = generate_text(prompt_evaluation, generation_config_eval)
        

        return jsonify({"evaluation": evaluation})
    
    except Exception as e:
        
        return jsonify({"error": "Failed to evaluate content"}), 500

if __name__ == "__main__":
    app.run(port=3000, debug=True)
