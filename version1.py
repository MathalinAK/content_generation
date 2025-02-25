import os
import feedparser
import autogen
from dotenv import load_dotenv
import streamlit as st
from typing import List
from pytrends.request import TrendReq
import time

os.environ["AUTOGEN_USE_DOCKER"] = "False"

load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

config_list = [
    {
        "model": "gemini-pro",
        "api_type": "google",
        "api_key": GOOGLE_API_KEY,
    }
]

llm_config = {"config_list": config_list, "code_execution_config": {"use_docker": False}}

class TopicsItem:
    def __init__(self, title, category):
        self.title = title
        self.category = category

def getgoogletopics_by_category(category: str, num_articles: int = 5) -> List[TopicsItem]:
    rss_url = f"https://news.google.com/rss/search?q={category}&gl=GB"
    feed = feedparser.parse(rss_url)
    return [TopicsItem(title=entry.title, category=category) for entry in feed.entries[:num_articles]]

def get_relevant_topics(query: str, num_articles: int = 5) -> List[TopicsItem]:
    rss_url = f"https://news.google.com/rss/search?q={query}&gl=GB"
    feed = feedparser.parse(rss_url)
    return [TopicsItem(title=entry.title, category="others") for entry in feed.entries[:num_articles]]
def get_google_trends():
    try:
        pytrends = TrendReq(hl="en-US", tz=360)
        time.sleep(1) 
        trending_searches = pytrends.trending_searches().head(5) 
        return trending_searches[0].tolist()
    except Exception as e:
        return ["Error fetching trends: " + str(e)]


writer = autogen.AssistantAgent(
    name="Writer",
    llm_config=llm_config,
    system_message="You generate high-quality content based on the given topic."
)

seo_reviewer = autogen.AssistantAgent(
    name="SEO Reviewer",
    llm_config=llm_config,
    system_message="Provide three key SEO recommendations to improve keyword placement, readability, and ranking potential. Do NOT rewrite content."
)

ethics_reviewer = autogen.AssistantAgent(
    name="Ethics Reviewer",
    llm_config=llm_config,
    system_message="Identify potential bias, fairness, and transparency concerns in content. Do NOT rewrite content."
)

def evaluate_content(content: str, aspect: str) -> float:
    eval_prompt = f"Evaluate the {aspect} of the following content on a scale of 0 to 100. Return only the number:\n\n{content}"
    score_response = writer.generate_reply(messages=[{"role": "user", "content": eval_prompt}])
    score = score_response.get("content") or score_response["choices"][0]["message"]["content"]
    try:
        return float(score.strip())
    except ValueError:
        return 50.0  

def get_feedback(content: str) -> str:
    relevance_score = evaluate_content(content, "relevance to topic")
    engagement_score = evaluate_content(content, "clarity and engagement")
    ethics_score = evaluate_content(content, "ethical integrity")
    overall_score = (relevance_score + engagement_score + ethics_score) / 3  
    seo_feedback = seo_reviewer.generate_reply(
        messages=[{"role": "user", "content": f"Give SEO feedback in 1-2 sentences:\n\n{content}"}]
    )["content"]
    ethics_feedback = ethics_reviewer.generate_reply(
        messages=[{"role": "user", "content": f"Give Ethics feedback in 1-2 sentences:\n\n{content}"}]
    )["content"]
    evaluation_table = f"""
    **Evaluation Scores:**

    | Evaluation Criteria        | Score  | Explanation                                   |
    |-------------------------|--------|-------------|  
    | **Relevance to Topic**   | {relevance_score}%  | Alignment with the given topic or prompt. |  
    | **Clarity & Engagement** | {engagement_score}%  | Audience engagement and clarity. |  
    | **Ethical Considerations** | {ethics_score}%  | Compliance with fairness and transparency. |  
    | **Overall Content Quality** | {overall_score}%  | Composite assessment of structure and effectiveness. |

    **SEO Recommendations:**
    {seo_feedback}

    **Ethical Review Comments:**
    {ethics_feedback}
    """
    return evaluation_table  

def generate_high_quality_content(topic: str):
    attempt = 0
    past_attempts = []
    best_content = ""
    best_score = 0
    content = ""  
    max_attempts = 3  
    while attempt < max_attempts:
        st.write(f"### Agent writer Attempt {attempt + 1}:")
        if attempt > 0:
            refinement_prompt = f"""
            Improve the following content by addressing these key points:
            - Increase relevance to "{topic}".
            - Improve clarity and engagement by refining the structure.
            - Address ethical concerns by ensuring fairness, balance, and transparency.

            Content:
            {content}

            Feedback:
            {feedback}
            """
            content_response = writer.generate_reply(messages=[{"role": "user", "content": refinement_prompt}])
        else:
            content_response = writer.generate_reply(
                messages=[{"role": "user", "content": f"Write a detailed and engaging blog post about: {topic}"}]
            )

        content = content_response.get("content")
        if not content:
            st.error("Failed to generate content. Please check your API key or quota.")
            return "", "", 0
        if content in past_attempts:
            st.warning("The AI is repeating itself. Adjusting the prompt for better results.")
            continue
        past_attempts.append(content)
        relevance_score = evaluate_content(content, "relevance to topic")
        engagement_score = evaluate_content(content, "clarity and engagement")
        ethics_score = evaluate_content(content, "ethical integrity")
        overall_score = (relevance_score + engagement_score + ethics_score) / 3  

        if attempt < 2:
            feedback = get_feedback(content)
        else:
            feedback = "Final version: No further feedback required."
        st.write("---")  
        st.subheader(f"Generated Content (Agent Writer Attempt {attempt + 1})")
        st.markdown(content, unsafe_allow_html=True)
        st.write("---")  
        st.subheader("Quality Score")
        st.write(f"**Score: {overall_score:.2f}%**")  
        st.divider()
        st.subheader(f"Agent Reviewer (Evaluation & Feedback {attempt + 1})")
        st.write(feedback)  
        st.write("---")  
        if overall_score > best_score:
            best_content = content
            best_score = overall_score
        if overall_score >= 95:
            break  
        else:
            attempt += 1  
    st.toast("Max attempts reached.")
    return best_content, best_score  

def main():
    st.title("AI-Powered Content Evaluator")
    trending_topics = get_google_trends()
    categories = ["Technology", "Sports", "Business", "Entertainment", "Tourism", "Others", "Trending Topics"]

    col1, col2 = st.columns([1, 2])

    with col1:
        selected_category = st.radio("Select a category:", categories)
        user_input = None

        if selected_category == "Others":
            user_input = st.text_input("Enter a custom topic:")
        elif selected_category == "Trending Topics":
            st.write("Current Google Trends:")
            for idx, trend in enumerate(trending_topics, start=1):
                st.write(f"{idx}. {trend}")

        if st.button("Fetch Topics"):
            category_query = user_input if selected_category == "Others" else selected_category

            with st.spinner(f"Fetching {category_query} topics..."):
                if selected_category == "Others" and user_input:
                    topics_items = get_relevant_topics(user_input)
                elif selected_category == "Trending Topics": 
                    topics_items = get_relevant_topics(trending_topics[0]) 
                else:
                    topics_items = getgoogletopics_by_category(selected_category)
            
            if not topics_items:
                st.write("No topics found.")
                return

            st.session_state.topics_items = topics_items

    with col2:
        if 'topics_items' in st.session_state:
            topics_titles = [item.title for item in st.session_state.topics_items]
            selected_title = st.radio("Select an article:", topics_titles)
            st.session_state.selected_topics = next(item for item in st.session_state.topics_items if item.title == selected_title)

    if 'selected_topics' in st.session_state:
        selected_topics = st.session_state.selected_topics

        with st.spinner("Generating content..."):
            high_quality_content, score = generate_high_quality_content(selected_topics.title)

        st.subheader("Final Content (After Evaluation & Refinement)")
        st.markdown(high_quality_content, unsafe_allow_html=True)
        st.subheader("Final Quality Score")
        st.write(f"**Score: {score}%**")


if __name__ == "__main__":
    main()
