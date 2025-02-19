import os
import feedparser
from dotenv import load_dotenv
import google.generativeai as genai
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from typing import TypedDict, List
import streamlit as st
from langgraph.graph import StateGraph

load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

def setup_gemini():
    genai.configure(api_key=GOOGLE_API_KEY)
    return ChatGoogleGenerativeAI(model="gemini-pro", temperature=0.7, google_api_key=GOOGLE_API_KEY)

class NewsItem:
    def __init__(self, title, category):
        self.title = title
        self.category = category

class State(TypedDict):
    categories: List[str]
    selected_category: str
    news_items: List[NewsItem]
    selected_news: NewsItem
    content_draft: str
    review_feedback: str
    user_input: str

def get_google_news_by_category(category: str, num_articles: int = 5) -> List[NewsItem]:
    query = category
    rss_url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
    feed = feedparser.parse(rss_url)
    
    news_items = []
    for entry in feed.entries[:num_articles]:
        news_items.append(NewsItem(title=entry.title, category=category))
    return news_items

def get_relevant_news(query: str, num_articles: int = 5) -> List[NewsItem]:
    rss_url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
    feed = feedparser.parse(rss_url)
    
    news_items = []
    for entry in feed.entries[:num_articles]:
        news_items.append(NewsItem(title=entry.title, category="others"))
    return news_items

def fetch_news_for_category_agent(state: State) -> State:
    if not state.get("selected_category"):
        return state
    category = state["selected_category"]
    news_items = get_google_news_by_category(category, num_articles=5)
    existing_items = [item for item in state.get("news_items", []) 
                     if item.category != category]
    state["news_items"] = existing_items + news_items
    return state

def fetch_news_for_others_category(state: State) -> State:
    if not state.get("selected_category") or state["selected_category"] != "others":
        return state
    
    # Get the user input and fetch relevant news
    user_input = state.get("user_input", "")
    if user_input:
        news_items = get_relevant_news(user_input, num_articles=5)
        state["news_items"] = news_items
    return state

def content_creator_agent(state: State) -> State:
    if not state.get("selected_news"):
        return state
    llm = setup_gemini()
    response = llm.invoke([
        HumanMessage(content=f"Write detailed content about this news: {state['selected_news'].title}. Include relevant analysis and background information.")
    ])
    state["content_draft"] = response.content
    return state

def content_reviewer_agent(state: State) -> State:
    if not state.get("content_draft"):
        return state
    llm = setup_gemini()
    response = llm.invoke([ 
        HumanMessage(content=f"Review this content and give constructive feedback:\n{state['content_draft']}") 
    ])
    state["review_feedback"] = response.content
    return state
    

def main():
    st.title("Content Generator")
    
    if not GOOGLE_API_KEY:
        st.error("Missing GOOGLE_API_KEY in .env file")
        return
    if 'state' not in st.session_state:
        st.session_state.state = State(
            categories=["Technology", "Business", "Food", "Entertainment", "Sports", "Tourism", "others"],
            selected_category="",
            news_items=[],
            selected_news=None,
            content_draft="",
            review_feedback="",
            user_input=""
        )
        st.session_state.news_fetched = False
        st.session_state.content_generated = False
        st.session_state.feedback_generated = False
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("Categories")
        selected_category = st.radio(
            "Select a category:",
            st.session_state.state["categories"]
        )
        if selected_category == "others":
            # If 'others' is selected, show the input box for user input
            user_input = st.text_input("Enter a topic:")
            if user_input:
                st.session_state.state["user_input"] = user_input

        if st.button(f"Show {selected_category.capitalize()} topics"):
            st.session_state.state["selected_category"] = selected_category

            st.session_state.news_fetched = True
            st.session_state.content_generated = False
            st.session_state.feedback_generated = False
            
            category_workflow = StateGraph(State)
            if selected_category == "others" and st.session_state.state["user_input"]:
                category_workflow.add_node("fetch_others_news", fetch_news_for_others_category)
            else:
                category_workflow.add_node("fetch_category_news", fetch_news_for_category_agent)
            
            category_workflow.set_entry_point("fetch_others_news" if selected_category == "others" else "fetch_category_news")
            compiled_category_workflow = category_workflow.compile()
        
            with st.spinner(f"Fetching {selected_category} news..."):
                result_state = compiled_category_workflow.invoke(st.session_state.state)
                st.session_state.state["news_items"] = result_state["news_items"]
    
    with col2:
        if st.session_state.news_fetched and st.session_state.state["selected_category"]:
            current_category = st.session_state.state["selected_category"]
            st.subheader(f"{current_category.capitalize()} News")
            
            category_news = [
                item for item in st.session_state.state["news_items"] 
                if item.category == current_category
            ]
            
            if category_news:
                news_titles = [item.title for item in category_news]
                selected_title = st.radio(
                    f"Select a {current_category} news article:",
                    news_titles
                )
                selected_news = next(
                    (item for item in category_news if item.title == selected_title),
                    None
                )
                
                if selected_news:
                    st.session_state.state["selected_news"] = selected_news
                    if st.button(f"Generate Content for this article"):
                        with st.spinner("Generating content..."):
                            content_workflow = StateGraph(State)
                            content_workflow.add_node("create_content", content_creator_agent)
                            content_workflow.set_entry_point("create_content")
                            compiled_content_workflow = content_workflow.compile()
                            

                            result_state = compiled_content_workflow.invoke(st.session_state.state)
                            st.session_state.state["content_draft"] = result_state["content_draft"]
                            st.session_state.content_generated = True
                            st.session_state.feedback_generated = False
            else:
                st.write("No news articles found for this category")
        elif not st.session_state.news_fetched:
            st.info("Please select a category and click 'Show topics' to view articles")
    
    if st.session_state.content_generated and st.session_state.state.get("selected_news"):
        st.subheader(f"Generated Content for: {st.session_state.state['selected_news'].title}")
        st.write(st.session_state.state["content_draft"])
    
        if not st.session_state.feedback_generated and st.button("Get Feedback on this Content"):
            with st.spinner("Generating expert feedback..."):
                review_workflow = StateGraph(State)
                review_workflow.add_node("review_content", content_reviewer_agent)
                review_workflow.set_entry_point("review_content")
                compiled_review_workflow = review_workflow.compile()
                result_state = compiled_review_workflow.invoke(st.session_state.state)
                st.session_state.state["review_feedback"] = result_state["review_feedback"]
                st.session_state.feedback_generated = True
    if st.session_state.feedback_generated:
        st.subheader("Expert Review Feedback")
        st.write(st.session_state.state["review_feedback"])

if __name__ == "__main__":
    main()
