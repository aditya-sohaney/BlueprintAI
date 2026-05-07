"""LLM-powered natural language Q&A over extracted drawing data."""

import json
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from core.database import DrawingDatabase


class DrawingChatAgent:
    """Natural language interface for querying extracted drawing data.

    Uses Claude API to interpret questions and generate SQL/pandas queries.
    """

    def __init__(self, db_path: str = None):
        load_dotenv()
        self.db = DrawingDatabase(db_path)
        self.df = self.db.export_to_dataframe()

        # Convert dates for analysis
        for col in ["initial_date", "final_date", "rfc_date"]:
            if col in self.df.columns:
                self.df[col] = pd.to_datetime(
                    self.df[col], format="%m/%d/%Y", errors="coerce"
                )

        self._init_llm()

    def _init_llm(self):
        """Initialize the LLM client."""
        try:
            import anthropic
            self.client = anthropic.Anthropic()
            self.model = "claude-sonnet-4-20250514"
        except Exception:
            self.client = None

    def _get_schema_description(self) -> str:
        """Generate a description of the available data for the LLM."""
        cols = list(self.df.columns)
        sample = self.df.head(3).to_string()
        return f"""Available columns: {cols}

Sample data (first 3 rows):
{sample}

Total rows: {len(self.df)}

Key columns:
- drawing_title: Title of the engineering drawing
- firm: Engineering firm name
- engineer_stamp_name: Engineer who stamped the drawing
- initial_date, final_date, rfc_date: Key milestone dates
- design_duration_days: Days from initial to final
- rfc_duration_days: Days from initial to RFC
- is_bridge_drawing: Boolean, True if bridge drawing
- rw_number: Retaining wall number (e.g., RW-003.107)
- division: ADOT division (BUILDER GROUP or ROADWAY DESIGN SERVICES)
- milepost: Station range along the corridor"""

    def ask(self, question: str) -> str:
        """Answer a natural language question about the drawing data.

        Args:
            question: The question in plain English.

        Returns:
            Answer string with data analysis results.
        """
        if self.client is None:
            return self._answer_locally(question)

        schema = self._get_schema_description()
        prompt = f"""You are a data analyst helping answer questions about ADOT engineering drawings.

{schema}

The user's question: {question}

Write Python pandas code to answer this question using the DataFrame `df`.
Return ONLY the code wrapped in ```python``` tags. The code should print the answer.
Do not import anything - df is already available as a pandas DataFrame with dates already parsed."""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )

        code_text = response.content[0].text

        # Extract code from markdown
        import re
        code_match = re.search(r'```python\s*(.*?)\s*```', code_text, re.DOTALL)
        if code_match:
            code = code_match.group(1)
        else:
            code = code_text

        # Execute the code
        try:
            import io
            import contextlib
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exec(code, {"df": self.df, "pd": pd})
            return output.getvalue().strip()
        except Exception as e:
            return f"Error executing analysis: {e}\nGenerated code:\n{code}"

    def _answer_locally(self, question: str) -> str:
        """Answer common questions without LLM using pattern matching."""
        q = question.lower()

        if "bridge" in q and ("how many" in q or "count" in q or "which" in q):
            bridges = self.df[self.df["is_bridge_drawing"] == True]
            walls = self.df[self.df["is_bridge_drawing"] == False]
            return f"Bridge drawings: {len(bridges)}, Retaining wall drawings: {len(walls)}"

        if "firm" in q and ("most" in q or "distribution" in q):
            return str(self.df["firm"].value_counts().to_string())

        if "engineer" in q and ("shortest" in q or "fastest" in q):
            eng = self.df.groupby("engineer_stamp_name")["design_duration_days"].mean()
            return f"Fastest engineer: {eng.idxmin()} ({eng.min():.0f} avg days)"

        if "engineer" in q and ("longest" in q or "slowest" in q):
            eng = self.df.groupby("engineer_stamp_name")["design_duration_days"].mean()
            return f"Slowest engineer: {eng.idxmax()} ({eng.max():.0f} avg days)"

        if "average" in q and ("time" in q or "duration" in q or "design" in q):
            avg = self.df["design_duration_days"].dropna().mean()
            return f"Average design duration: {avg:.1f} days"

        return ("I can answer questions about firms, engineers, design durations, "
                "bridge vs wall counts, and more. Try asking a specific question.")

    def close(self):
        """Clean up resources."""
        self.db.close()
