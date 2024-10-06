import streamlit as st
import time
import sys
import os
import base64
from st_weaviate_connection import WeaviateConnection, WeaviateFilter
from weaviate.classes.query import Filter

# Constants
ENV_VARS = ["WEAVIATE_URL", "WEAVIATE_API_KEY", "COHERE_API_KEY"]
NUM_RECOMMENDATIONS_PER_ROW = 5
SEARCH_LIMIT = 10

# Search Mode descriptions
SEARCH_MODES = {
    "Keyword": ("Looking for a classic keyword search? The BM25 algorithm ranks movies based on how often your keywords appear.", 0),
    "Semantic": ("Want to find films based on their overall meaning? The semantic (vector) search fetches results closest to your search context.", 1),
    "Hybrid": ("Can't decide? The Hybrid search merges both keyword and semantic results for the best of both worlds!", 0.7),
}

# Functions
def get_env_vars(env_vars):
    """Retrieve environment variables"""
    env_vars = {var: os.environ.get(var, "") for var in env_vars}
    for var, value in env_vars.items():
        if not value:
            st.error(f"{var} not set", icon="🚨")
            sys.exit(f"{var} not set")
    return env_vars

def display_chat_messages():
    """Show message history in the chat interface"""
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if "images" in message:
                for i in range(0, len(message["images"]), NUM_RECOMMENDATIONS_PER_ROW):
                    cols = st.columns(NUM_RECOMMENDATIONS_PER_ROW)
                    for j, col in enumerate(cols):
                        if i + j < len(message["images"]):
                            col.image(message["images"][i + j], width=200)
            if "titles" in message:
                for i in range(0, len(message["titles"]), NUM_RECOMMENDATIONS_PER_ROW):
                    cols = st.columns(NUM_RECOMMENDATIONS_PER_ROW)
                    for j, col in enumerate(cols):
                        if i + j < len(message["titles"]):
                            col.write(message["titles"][i + j])

def base64_to_image(base64_str):
    """Convert base64 string to image"""
    return f"data:image/png;base64,{base64_str}"

def clean_input(input_text):
    """Clean user input by removing unnecessary characters"""
    return input_text.replace('"', "").replace("'", "")

def setup_sidebar():
    """Customize sidebar elements"""
    with st.sidebar:
        st.title("🎬 Movie Magic Hub")
        st.subheader("Your AI-powered Film Recommender 🎥")
        st.markdown("Looking for the perfect movie for your night? Powered by Weaviate & AI, we’ve got you covered. Tell us what you're in the mood for, and we'll suggest something fantastic!")
        st.header("Settings")

        mode = st.radio("Select Search Mode", options=list(SEARCH_MODES.keys()), index=2)
        year_range = st.slider("Choose a Year Range", min_value=1950, max_value=2024, value=(1990, 2024))
        st.info(SEARCH_MODES[mode][0])
        st.success("Connected to Weaviate successfully!", icon="💚")

    return mode, year_range

def setup_weaviate_connection(env_vars):
    """Establish Weaviate connection"""
    return st.connection(
        "weaviate",
        type=WeaviateConnection,
        url=env_vars["https://hha2nvjsruetknc5vxwrwa.c0.europe-west2.gcp.weaviate.clod"],
        api_key=env_vars["nMZuw1z1zvtnjkXXOMGx90ws7YWGSsakItdus"],
        additional_headers={"X-Cohere-Api-Key": env_vars["JaLagsYZvL2KgTDfuXBtifi4uGj8Qz07WUbrjNzq"]},
    )

def display_example_prompts():
    """Show predefined example prompts to make interaction easier"""
    example_prompts = [
        ("Sci-fi adventure", "movie night with friends"),
        ("Romantic comedy", "date night"),
        ("Animated family film", "family viewing"),
        ("Classic thriller", "solo movie night"),
        ("Historical drama", "educational evening"),
        ("Indie comedy-drama", "film club discussion"),
    ]

    example_prompts_help = [
        "Looking for sci-fi adventures? Perfect for a group movie night!",
        "Romantic comedies for the perfect date night.",
        "Animated films for a fun family evening.",
        "Thrillers that'll keep you on the edge of your seat, just for you.",
        "Dramatic and educational movies to broaden your horizons.",
        "Indie gems to spark discussions at your film club.",
    ]

    st.markdown("---")
    st.write("Need some ideas? Choose an example prompt or type your own, then **hit 'Search'** to get recommendations!")

    button_cols = st.columns(3)
    button_cols_2 = st.columns(3)

    for i, ((movie_type, occasion), help_text) in enumerate(zip(example_prompts, example_prompts_help)):
        col = button_cols[i] if i < 3 else button_cols_2[i-3]
        if col.button(f"{movie_type} for {occasion}", help=help_text):
            st.session_state.example_movie_type = movie_type
            st.session_state.example_occasion = occasion
            return True
    return False

def perform_search(conn, movie_type, rag_prompt, year_range, mode):
    """Perform movie search and show results"""
    df = conn.query(
        "MovieDemo",
        query=movie_type,
        return_properties=["title", "tagline"],
        filters=(
            WeaviateFilter.by_property("release_year").greater_or_equal(year_range[0]) &
            WeaviateFilter.by_property("release_year").less_or_equal(year_range[1])
        ),
        limit=SEARCH_LIMIT,
        alpha=SEARCH_MODES[mode][1],
    )

    images = []
    titles = []

    if df is None or df.empty:
        with st.chat_message("assistant"):
            st.write(f"Sorry, no movies matched your search for {movie_type} using {mode} mode. Try adjusting your search!")
        st.session_state.messages.append({"role": "assistant", "content": "No movies found. Try again with different keywords!"})
        return
    else:
        with st.chat_message("assistant"):
            st.write("Here’s what I found for you!")
            cols = st.columns(NUM_RECOMMENDATIONS_PER_ROW)
            for index, row in df.iterrows():
                col = cols[index % NUM_RECOMMENDATIONS_PER_ROW]
                if "poster" in row and row["poster"]:
                    col.image(base64_to_image(row["poster"]), width=200)
                    images.append(base64_to_image(row["poster"]))
                else:
                    col.write(f"{row['title']}")
                    titles.append(row["title"])

            st.write("Generating your tailored recommendation...")

        st.session_state.messages.append(
            {"role": "assistant", "content": "Here's your recommendation:", "images": images, "titles": titles}
        )

        with conn.client() as client:
            collection = client.collections.get("MovieDemo")
            response = collection.generate.hybrid(
                query=movie_type,
                filters=(
                    Filter.by_property("release_year").greater_or_equal(year_range[0]) &
                    Filter.by_property("release_year").less_or_equal(year_range[1])
                ),
                limit=SEARCH_LIMIT,
                alpha=SEARCH_MODES[mode][1],
                grouped_task=rag_prompt,
                grouped_properties=["title", "tagline"],
            )

            rag_response = response.generated

            with st.chat_message("assistant"):
                message_placeholder = st.empty()
                full_response = ""
                for chunk in rag_response.split():
                    full_response += chunk + " "
                    time.sleep(0.02)
                    message_placeholder.markdown(full_response + "▌")
                message_placeholder.markdown(full_response)

        st.session_state.messages.append(
            {"role": "assistant", "content": "Based on your search, here’s what I recommend: " + full_response}
        )

def main():
    st.title("🎬 Welcome to Movie Magic Hub!")

    env_vars = get_env_vars(ENV_VARS)
    conn = setup_weaviate_connection(env_vars)
    mode, year_range = setup_sidebar()

    if "messages" not in st.session_state:
        st.session_state.messages = []
        st.session_state.greetings = False

    display_chat_messages()

    if not st.session_state.greetings:
        with st.chat_message("assistant"):
            intro = "👋 Hi there! I’m your friendly movie recommender. Let me know what genre or type of movie you’re in the mood for, and I’ll suggest the best options!"
            st.markdown(intro)
            st.session_state.messages.append({"role": "assistant", "content": intro})
            st.session_state.greetings = True

    if "example_movie_type" not in st.session_state:
        st.session_state.example_movie_type = ""
    if "example_occasion" not in st.session_state:
        st.session_state.example_occasion = ""

    example_selected = display_example_prompts()

    movie_type = clean_input(st.text_input(
        "What type of movies are you searching for?",
        value=st.session_state.example_movie_type,
        placeholder="E.g., action, romance, documentary..."
    ))

    viewing_occasion = clean_input(st.text_input(
        "What’s the occasion?",
        value=st.session_state.example_occasion,
        placeholder="E.g., movie night with friends, date night..."
    ))

    if st.button("Search") or example_selected:
        with st.chat_message("user"):
            movie_type_message = f"I'm looking for a **{movie_type}** movie."
            if viewing_occasion:
                movie_type_message += f" It’s for a **{viewing_occasion}**."
            st.markdown(movie_type_message)
            st.session_state.messages.append({"role": "user", "content": movie_type_message})

        perform_search(conn, movie_type, viewing_occasion, year_range, mode)

if __name__ == "__main__":
    main()
