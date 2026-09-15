# 🚀 [GridGuard Operations Control]
---

## 👥 Team

| Field | Value |
|---|---|
| **Team Name** | [Arcturus] |
| **Track** | [AI] |
| **Team Lead** | [Om patel] — [email@ibm.com] |
| **Members** | [Gyan Patel], [Pratham Patel], [Smit Tandel] |

---

## 🎯 Problem Statement

> In 2–3 sentences: What problem does your project solve? Who experiences this problem?

[During intense storm events across major utility sectors in Gujarat, grid operations desks face extreme visibility issues because live sensor data, localized weather data, and crew logs are completely split across disconnected software tools. When high-voltage infrastructure begins failing under environmental stress, control rooms lack a single unified tool to process real-time satellite captures and calculate immediate equipment threat variables. This missing link forces engineers to act blindly, extends cascade power blackout durations, and leaves emergency field teams stranded in dangerous territory without predictive route profiling.
]

---

## 💡 Solution

> In 2–3 sentences: What did you build? How does it solve the problem above?

[We built **GridGuard**, a high-efficiency power management web application running a Django REST Framework backend coupled to an animated Vanilla HTML/CSS/JS topological operations timeline canvas. 

The core system enables operators to drag and drop raw satellite screen captures directly onto the operational interface. The Django application translates the pixel arrays using an offline machine learning logic model (`.pkl`) to extract instant regional rainfall metrics. Simultaneously, the system queries the live open-source Open-Meteo API using coordinate vectors to inject ambient environmental parameters (wind thresholds and temperatures) straight into a composite asset evaluation calculation. 

This results in an instant 0–100% Outage Risk rating map accompanied by an animated vertical transit pipeline that visually guides emergency crews to high-threat grid components before cascade failures occur.]

---

## ✨ Key Features

- **Satellite Image Inference:** Processes uploaded geographical weather map captures through a Python machine learning model (`.pkl`) to predict localized rainfall intensity in millimeters.
- **Live Environmental Synthesis:** Dynamically queries the open-source Open-Meteo API using coordinate vectors to fetch real-time temperature and wind speed variables.]
- **Proximity Fallback Routing:** Automatically calculates a distance matrix map to pull historical data from the nearest available city profile if the exact location profile doesn't exist in our JSON database.
- **Operator Synchronization Controls:** Features a manual "Sync Now" button trigger that controls API requests, protecting the platform from network timeout rate limits during emergencies.
- **Animated Transit Pipeline:** Replaces traditional boring table structures with an animated, glowing vertical pipeline tracking field crew hubs, target destinations, and diagnostic task details.

---

## 🛠️ Tech Stack

| Category | Technologies |
|---|---|
| **Languages** | [Python,Javascript,HTML,CSS] |
| **Frameworks** | [Django, Django REST Framework] |
| **IBM Technologies** | [IBM Bob] |
| **Databases** | [Local JSON Data Arrays] |
| **Other** | [Joblib, Scikit-Learn, Numpy, Pandas, Pillow, Requests, django-cors-headers] |

---

## 📁 Repository Structure

```
├── src/                  # All source code
├── docs/                 # Written documentation
│   ├── problem-statement.md
│   ├── solution-overview.md
│   ├── architecture.md
│   └── setup-guide.md
├── demo/                 # Demo artifacts
│   ├── screenshots/      # App screenshots
│   └── demo-video-link.txt  # Link to demo video
├── presentation/         # Slide deck
└── submission.yaml       # Structured submission metadata
```

---

## ⚡ How to Run

> **Copy these exact steps from your [`docs/setup-guide.md`](docs/setup-guide.md)**

```bash
# 1. Clone the repo
git clone https://github.com/bob-ai-hackathon-Arcturus.git
cd bob-ai-hackathon-Arcturus

# 2. Install dependencies
# Tab A: Set up and install backend python libraries
cd src/backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install django djangorestframework django-cors-headers joblib scikit-learn pillow pandas requests

# 3. Configure environment
# Copy the baseline layout settings file inside /src/
# Windows: cp src/.env.example src/.env
# Edit src/.env with your local values if needed

# 4. Run the project
# Tab A (Backend Django Server):
python manage.py runserver

# Tab B (Frontend Static File Web Server - Open a new terminal tab):
cd src/frontend
python -m http.server 5500      if it says not fount then visit=>( http://124.0.0.1:5500/overview.html )


## 🖥️ Demo

| Artifact | Link |
|---|---|
| 📹 Demo Video | [See demo/demo-video-link.txt](demo/demo-video-link.txt) |
| 🌐 Live Demo | [See demo/live-demo-url.txt](demo/live-demo-url.txt) |
| 🖼️ Screenshots | [See demo/screenshots/](demo/screenshots/) |
| 📊 Presentation | [See presentation/slides.pdf](presentation/) |

---

## ⚠️ Known Limitations

> Be honest — judges appreciate transparency over overclaiming.

- **Containerization:** Docker implementation was not possible within the hackathon timeline constraints, so automated container installation instructions have been removed from the setup documentation.
- **Mobile Support:** A mobile version was not created; the dashboard is strictly optimized for desktop command centers.
- **Live Satellite Stream:** We were unable to apply live satellite API fetching due to access token restrictions,and access to real data , so the engine relies on processing static image uploads and fallback zip bundles instead.

---

## 🏅 What We're Most Proud Of

[We are super proud of how our features work together to solve real problems. Instead of just showing standard weather values, we connected a customized python machine learning model directly to a file drop container so operators can extract rainfall statistics straight out of static images. We also built a clever closest-coordinate lookup system that acts as a safety guardrail. If an asset folder is completely missing its historical data profile during a storm, our code automatically calculates the distance matrix to load information from the nearest available city so the grid monitoring panels stay online. Finally, turning off the automatic polling background timers and locking our data fetches directly to our manual 'Sync Now' click listener keeps our application highly performance-efficient and completely safe from network timeout rate limits during testing.
]

---
