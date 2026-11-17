# Diabetic-retinopathy

## System Architecture Diagram
A high-quality system architecture diagram has been generated for the project:
- **System Architecture Infographic**: [Open diagram_viz/system_architecture.html](./diagram_viz/system_architecture.html) (Frontend/Backend Split).
- **Documentation**: [architecture_diagram.md](./architecture_diagram.md) (Mermaid).

## Web Application (Working Model)
A complete working prototype of the diagnostic pipeline has been implemented in the `app/` directory.

### Features
- **Frontend**: Medical-grade Upload Interface & Interactive Dashboard (HTML/CSS/JS).
- **Backend**: Python Flask connecting VGG16 (Feature Extraction) and XGBoost (Classification).
- **Visualization**: Chart.js integration for Risk and Probability graphs.

### How to Run
1. Create and activate a Python virtual environment (PowerShell):
   ```bash
   py -m venv venv
   .\venv\Scripts\Activate.ps1
   ```
   Run this step once; if your prompt already starts with `(venv)`, skip it.
2. Install the Python dependencies:
   ```bash
   python -m pip install -r requirements.txt
   ```
3. Start the Flask server from the project root:
   ```bash
   npm run dev
   ```
   Alternatively, run it directly:
   ```bash
   cd app
   py app.py
   ```
4. Open your browser at `http://localhost:3000`. Patient and diagnosis records are stored in `app/instance/retina_ai.db`.


