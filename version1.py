import os
import feedparser
from dotenv import load_dotenv
import google.generativeai as genai
from typing import List
import streamlit as st

# Load environment variables
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Configure Gemini Pro
genai.configure(api_key=GOOGLE_API_KEY)
gemini_model = genai.GenerativeModel('gemini-pro')

# Define a function to interact with Gemini Pro
def generate_with_gemini(prompt: str) -> str:
    response = gemini_model.generate_content(prompt)
    return response.text

class NewsItem:
    def __init__(self, title, category):
        self.title = title
        self.category = category

# Fetch news articles
def get_news_by_category(category: str, num_articles: int = 5) -> List[NewsItem]:
    query = category if category != "others" else st.session_state.get("user_input", "")
    rss_url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
    feed = feedparser.parse(rss_url)
    return [NewsItem(title=entry.title, category=category) for entry in feed.entries[:num_articles]]

class Agent:
    def __init__(self, name, system_prompt):
        self.name = name
        self.system_prompt = system_prompt

    def generate_response(self, prompt: str) -> str:
        full_prompt = f"{self.system_prompt}\n\n{prompt}"
        return generate_with_gemini(full_prompt)

# Initialize agents
writer = Agent(
    name="Writer",
    system_prompt="You are a writer who creates engaging and informative content. "
                  "You analyze news articles and create detailed, well-structured content. "
                  "You must polish your writing based on feedback and provide refined versions.",
)

seo_reviewer = Agent(
    name="SEOReviewer",
    system_prompt="You are an SEO expert who reviews content for search optimization. "
                  "Provide concise, actionable feedback in 3 bullet points about keyword usage, "
                  "structure, and visibility. Begin with 'SEO Review:'",
)

style_reviewer = Agent(
    name="StyleReviewer",
    system_prompt="You are a writing style expert who reviews content for clarity and engagement. "
                  "Provide concise, actionable feedback in 3 bullet points about tone, flow, and clarity. "
                  "Begin with 'Style Review:'",
)

legal_reviewer = Agent(
    name="LegalReviewer",
    system_prompt="You are a legal expert who reviews content for compliance and potential issues. "
                  "Provide concise, actionable feedback in 3 bullet points about legal concerns. "
                  "Begin with 'Legal Review:'",
)

meta_reviewer = Agent(
    name="MetaReviewer",
    system_prompt="You are a meta reviewer who aggregates feedback from other reviewers "
                  "and provides final, actionable recommendations for improvement. "
                  "Begin with 'Final Recommendations:'",
)

def main():
    st.title("AI Content Generator with Feedback Loop")

    if not GOOGLE_API_KEY:
        st.error("Missing GOOGLE_API_KEY in .env file")
        return

    if 'generation_count' not in st.session_state:
        st.session_state.generation_count = 0
    if 'iterations' not in st.session_state:
        st.session_state.iterations = []

    col1, col2 = st.columns([1, 2])

    with col1:
        st.subheader("Select Topic")
        categories = ["Technology", "Business", "Entertainment", "Sports", "others"]
        selected_category = st.radio("Category:", categories)

        if selected_category == "others":
            user_input = st.text_input("Enter topic:")
            if user_input:
                st.session_state.user_input = user_input

    if selected_category:
        with st.spinner("Fetching news..."):
            news_items = get_news_by_category(selected_category)

        with col2:
            st.subheader("Select Article")
            if news_items:
                selected_title = st.radio(
                    "Choose an article:",
                    [item.title for item in news_items]
                )

                if selected_title:
                    selected_news = next(
                        (item for item in news_items if item.title == selected_title),
                        None
                    )

                    if selected_news:
                        if st.button("Generate & Refine Content"):
                            with st.spinner("Generating content and reviews..."):
                                st.session_state.iterations = []
                                content = writer.generate_response(f"Write a detailed article about: {selected_news.title}")

                                for i in range(3):
                                    reviews = {
                                        "SEOReviewer": seo_reviewer.generate_response(content),
                                        "StyleReviewer": style_reviewer.generate_response(content),
                                        "LegalReviewer": legal_reviewer.generate_response(content),
                                    }

                                    reviews_summary = "\n".join(reviews.values())
                                    final_recommendations = meta_reviewer.generate_response(
                                        f"Aggregate the following reviews and provide final recommendations:\n\n{reviews_summary}"
                                    )

                                    st.session_state.iterations.append({
                                        'content': content,
                                        'reviews': reviews,
                                        'final_recommendations': final_recommendations
                                    })

                                    refinement_prompt = (
                                        f"Refine the following content based on these final recommendations:\n\n"
                                        f"Content:\n{content}\n\n"
                                        f"Final Recommendations:\n{final_recommendations}\n\n"
                                        "Please produce a polished and improved version of the content."
                                    )
                                    content = writer.generate_response(refinement_prompt)

                                    st.session_state.generation_count += 1

    if 'iterations' in st.session_state:
        for i, iteration in enumerate(st.session_state.iterations):
            st.subheader(f"Generated Content - Iteration {i + 1}")
            st.write(iteration['content'])

            with st.expander(f"View Feedback for Iteration {i + 1}", expanded=True):
                st.markdown("### Reviews and Recommendations")
                for reviewer, review in iteration['reviews'].items():
                    st.markdown(f"**{reviewer}**")
                    st.write(review)

                st.markdown("### Final Recommendations")
                st.write(iteration['final_recommendations'])

        if st.session_state.generation_count >= 3:
            st.warning("Maximum refinement iterations reached (3).")

if __name__ == "__main__":
    main()
