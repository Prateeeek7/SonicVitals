import sqlite3
import time
import csv
import os

class SessionDatabase:
    def __init__(self, db_path="sessions.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initializes SQLite database tables if they do not exist."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create Sessions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                timestamp INTEGER,
                participant_id TEXT,
                fps REAL,
                mic_rate INTEGER,
                fusion_strategy TEXT
            )
        """)
        
        # Create Physiological Data Log table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS physiological_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                timestamp_ms INTEGER,
                vis_hr REAL,
                vis_snr REAL,
                ac_rr REAL,
                ac_snr REAL,
                fused_hr REAL,
                fused_rr REAL,
                confidence REAL,
                FOREIGN KEY (session_id) REFERENCES sessions (session_id)
            )
        """)
        
        conn.commit()
        conn.close()

    def start_session(self, participant_id, fps=15.0, mic_rate=16000, fusion_strategy="Attention-ML"):
        """Creates a new session entry and returns its generated Session ID."""
        session_id = f"SESS_{int(time.time())}"
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            "INSERT INTO sessions (session_id, timestamp, participant_id, fps, mic_rate, fusion_strategy) VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, int(time.time()), participant_id, fps, mic_rate, fusion_strategy)
        )
        
        conn.commit()
        conn.close()
        return session_id

    def log_record(self, session_id, vis_hr, vis_snr, ac_rr, ac_snr, fused_hr, fused_rr, confidence):
        """Logs an instantaneous physiological measurement record."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO physiological_log 
            (session_id, timestamp_ms, vis_hr, vis_snr, ac_rr, ac_snr, fused_hr, fused_rr, confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (session_id, int(time.time() * 1000), vis_hr, vis_snr, ac_rr, ac_snr, fused_hr, fused_rr, confidence))
        
        conn.commit()
        conn.close()

    def get_session_summary(self, session_id):
        """Returns statistical averages (Mean HR, Mean RR, Avg Confidence) for a session."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT AVG(fused_hr), AVG(fused_rr), AVG(confidence)
            FROM physiological_log
            WHERE session_id = ?
        """, (session_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result and result[0] is not None:
            return {
                "mean_hr": round(result[0], 1),
                "mean_rr": round(result[1], 1),
                "avg_confidence": round(result[2] * 100.0, 1)
            }
        return {"mean_hr": 0.0, "mean_rr": 0.0, "avg_confidence": 0.0}

    def export_session_to_csv(self, session_id, output_dir="exports"):
        """Exports a session's detailed time series data to a CSV file."""
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        csv_file = os.path.join(output_dir, f"{session_id}_report.csv")
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT timestamp_ms, vis_hr, vis_snr, ac_rr, ac_snr, fused_hr, fused_rr, confidence
            FROM physiological_log
            WHERE session_id = ?
            ORDER BY timestamp_ms ASC
        """, (session_id,))
        
        records = cursor.fetchall()
        conn.close()
        
        if not records:
            print(f"No records found to export for session: {session_id}")
            return None

        with open(csv_file, mode='w', newline='') as f:
            writer = csv.writer(f)
            # Write Header
            writer.writerow(["Timestamp_MS", "Visual_HR_BPM", "Visual_SNR_dB", "Acoustic_RR_BreathsM", "Acoustic_SNR_dB", "Fused_HR_BPM", "Fused_RR_BreathsM", "Confidence_Ratio"])
            # Write rows
            writer.writerows(records)
            
        print(f"Session data successfully exported to {csv_file}")
        return csv_file

if __name__ == "__main__":
    # Test database standalone
    db = SessionDatabase("test_sessions.db")
    s_id = db.start_session("TEST_SUB")
    print(f"Started session: {s_id}")
    
    # Write mock logs
    for i in range(5):
        time.sleep(0.1)
        db.log_record(s_id, 72.0 + i, 8.5, 16.0 - (i*0.1), 9.2, 72.5 + i, 15.9, 0.95)
        
    summary = db.get_session_summary(s_id)
    print(f"Summary: Mean HR={summary['mean_hr']} BPM | Mean RR={summary['mean_rr']} Breaths/M | Avg Conf={summary['avg_confidence']}%")
    
    db.export_session_to_csv(s_id)
    # Clean up test file
    if os.path.exists("test_sessions.db"):
        os.remove("test_sessions.db")
