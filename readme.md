<div align="center">
  <img src="logo/lifelog_logo.svg" alt="LifeLog Logo" width="300" height="75">
  
  # LifeLog
  
  ![License](https://img.shields.io/badge/license-MIT-blue.svg)
  ![Python](https://img.shields.io/badge/python-3.8+-blue.svg)
  ![FastAPI](https://img.shields.io/badge/FastAPI-green.svg)
  ![React](https://img.shields.io/badge/React-18+-61dafb.svg)
  ![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15+-336791.svg)
  ![Docker](https://img.shields.io/badge/Docker-compose-2496ed.svg)
  ![AI](https://img.shields.io/badge/AI-Google%20Gemini-ff6b6b.svg)
  
  [![GitHub stars](https://img.shields.io/github/stars/jaxfry/lifelog?style=social)](https://github.com/jaxfry/lifelog/stargazers)
  [![GitHub forks](https://img.shields.io/github/forks/jaxfry/lifelog?style=social)](https://github.com/jaxfry/lifelog/network/members)
  
</div>

Ever get to the end of the day and wonder, "What did I *actually* do?" I built LifeLog to answer that question for myself.

It's a personal project that hooks into [ActivityWatch](https://activitywatch.net/) (an awesome open-source time tracker) to automatically log what I'm doing on my computer. Then, it uses a bit of AI magic (specifically, Google's Gemini) to turn that raw data stream into a clean, understandable timeline of my day.

While it started as a personal tool, the long-term vision is a **modular platform** where different components—like the AI model or data sources—can be easily swapped or extended. It's like a personal, automatically-written journal for my digital life.

> **⚠️ A Quick Heads-Up!**
>
> This is very much a **prototype** and a work-in-progress. I built it to see if the idea was even possible.
>
> Right now, it's not built with strong security or privacy in mind. The next major version will focus on a ground-up rewrite to be more **secure, private, and truly modular**, allowing for greater flexibility and customization. For now, think of this as a fun experiment! Also, it's sort of a pain to set up, so be prepared for that. 😅

## What can it do?

*   **Automatic Tracking**: It quietly watches your active windows and browser tabs via ActivityWatch.
*   **AI Summaries**: Turns a messy list of events like `(window: "VS Code"), (browser: "Stack Overflow")` into a clean entry like "Coding on the LifeLog project".
*   **Smart Project Grouping**: Tries to figure out which activities belong to the same project and groups them together for you.
*   **Simple Analytics**: Shows you a daily summary and a timeline so you can see where your time really went.

## How the Pieces Fit Together

The architecture is intentionally **modular**, with each service handling a distinct responsibility. This design means you could, for example, swap the `Processing Service` to use OpenAI instead of Gemini, or add a new `Ingestion Service` to pull data from another source. The goal is flexibility.

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   My Computer   │────│ Ingestion Service│────│Processing Service│
│  (ActivityWatch)│    │    (FastAPI)    │    │   (AI/LLM)     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                │                       │
                                └───────────────────────┼────────┐
                                                        │        │
┌─────────────────┐    ┌─────────────────┐    ┌─────────▼──┐   ┌─▼────┐
│   Web UI        │────│   API Service   │    │PostgreSQL │   │RabbitMQ│
│   (React/TS)    │    │   (FastAPI)     │    │ +pgvector  │   │        │
└─────────────────┘    └─────────────────┘    └────────────┘   └────────┘
```

## The Tech Stack

This project is built with some of my favorite tools:

*   **Backend**: FastAPI, SQLAlchemy, PostgreSQL with pgvector, RabbitMQ
*   **Frontend**: React, TypeScript, Tailwind CSS, Vite
*   **AI/ML**: Google Gemini API, Sentence Transformers
*   **Data Source**: ActivityWatch

## 🚀 Get it Running

1.  **Clone the repo:**
    ```bash
    git clone https://github.com/jaxfry/lifelog.git
    cd lifelog
    ```

2.  **Set up your environment:**
    ```bash
    # Copy the example environment file
    cp .env.example .env

    # Now, open .env and add your Google Gemini API key and configure any other settings you need.
    ```

3.  **Start everything with Docker:**
    ```bash
    docker-compose up --build
    ```

4.  **Check it out:**
    *   Frontend: [http://localhost:5173](http://localhost:5173)
    *   API Docs: [http://localhost:8000/api/v1/docs](http://localhost:8000/api/v1/docs)
    *   RabbitMQ (if you're curious): [http://localhost:15672](http://localhost:15672)

## 📱 Setting Up the Local Agent

You'll need to install a small agent on your computer that sends your ActivityWatch data to LifeLog's ingestion service.

```bash
# The installer will ask you a few questions to get set up.
./install.sh

# If you prefer to do it by hand:
cd local_daemon
pip install -r requirements.txt
python daemon.py
```

This agent will find your ActivityWatch data and start streaming it to the services you just launched.

## How it Actually Works

Each step in the process is designed as a separate logical component:

1.  **Collect (The Agent)**: The local daemon on your machine grabs your activity from the data source (currently ActivityWatch).
2.  **Ingest (The Gateway)**: It sends these raw events to a dedicated ingestion service, which acts as the front door to the system and queues them for processing.
3.  **Process (The Brain)**: A separate processing service pulls these events, bundles them up, and asks an AI (currently Gemini) "What was the user doing during this time?". This is the "pluggable" module for different AI models or summarization logic.
4.  **Display (The Interface)**: The React frontend calls the API to get the processed timeline and displays it for you.

## A Quick Rant About AI
Hey there! I'd like to let you know that for building this prototype, I used significant amounts of AI-generated code and documentation (including this README). This was my first time using AI in this way (ahem... vibecoding), and it was quite a learning experience. I realized how much AI can help with prototyping and speeding up development, but I also learned that it can dampen your understanding of the code itself, especially when I'm tired and just give up. While I feel like I still learned a significant amount, I feel like I could have learned more if I had written the code myself. In my next version, I plan to be more hands-on with the code as I try to move away from a prototyping version to a more production-ready one.

On another note, I want to be **super** clear about how AI was used in the project itself. I use AI in the data pipeline to help summarize the raw activity data using the Google Gemini API, but this obviously means that you have to willingly send your data to Google. In the next version (V1), I plan to make LifeLog compatible with other AI models, including locally hosted ones.

## License

This project is under the MIT License - see the [LICENSE](LICENSE) file for details.

---

Hope you find it useful! ✨