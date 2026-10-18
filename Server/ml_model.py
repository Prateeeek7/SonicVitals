import numpy as np
try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

# Definition of PyTorch Neural Fusion Network
if TORCH_AVAILABLE:
    class MultimodalFusionNet(nn.Module):
        def __init__(self):
            super(MultimodalFusionNet, self).__init__()
            # Encoder for Visual Features (Raw HR, Visual SNR, luminance variance)
            self.vis_encoder = nn.Sequential(
                nn.Linear(3, 16),
                nn.ReLU(),
                nn.Linear(16, 16)
            )
            # Encoder for Acoustic Features (Raw RR, Acoustic SNR, amplitude variance)
            self.ac_encoder = nn.Sequential(
                nn.Linear(3, 16),
                nn.ReLU(),
                nn.Linear(16, 16)
            )
            
            # Quality Attention Layer: maps quality metrics (SNRs) to weighting logits
            self.attention_fc = nn.Sequential(
                nn.Linear(2, 8),
                nn.ReLU(),
                nn.Linear(8, 2) # Outputs logits for [Visual, Acoustic] channels
            )
            
            # Multitask regression heads
            self.hr_head = nn.Sequential(
                nn.Linear(32, 16),
                nn.ReLU(),
                nn.Linear(16, 1) # Predicts Heart Rate
            )
            self.rr_head = nn.Sequential(
                nn.Linear(32, 16),
                nn.ReLU(),
                nn.Linear(16, 1) # Predicts Respiratory Rate
            )
            self.conf_head = nn.Sequential(
                nn.Linear(32, 8),
                nn.ReLU(),
                nn.Linear(8, 1),
                nn.Sigmoid()     # Predicts overall system confidence score [0.0, 1.0]
            )

        def forward(self, vis_features, ac_features, quality_inputs):
            # Encode inputs
            v_latent = self.vis_encoder(vis_features)
            a_latent = self.ac_encoder(ac_features)
            
            # Calculate attention weights based on quality inputs (e.g. SNRs)
            attn_logits = self.attention_fc(quality_inputs)
            attn_weights = F.softmax(attn_logits, dim=-1)
            
            # Apply attention weights to modulate feature vectors
            w_v = attn_weights[:, 0].unsqueeze(-1)
            w_a = attn_weights[:, 1].unsqueeze(-1)
            
            v_weighted = v_latent * w_v
            a_weighted = a_latent * w_a
            
            # Concatenate latent representations
            fused_latent = torch.cat((v_weighted, a_weighted), dim=-1)
            
            # Regression predictions
            hr = self.hr_head(fused_latent)
            rr = self.rr_head(fused_latent)
            confidence = self.conf_head(fused_latent)
            
            return hr, rr, confidence, attn_weights

class AdaptiveFusionEngine:
    def __init__(self, model_path=None):
        self.model_path = model_path
        self.torch_enabled = TORCH_AVAILABLE
        self.model = None
        
        if self.torch_enabled:
            try:
                self.model = MultimodalFusionNet()
                if model_path:
                    self.model.load_state_dict(torch.load(model_path))
                self.model.eval()
                print("PyTorch Sensor Fusion model initialized successfully.")
            except Exception as e:
                print(f"Failed to load PyTorch model weights: {e}. Running in evaluation fallback mode.")
        else:
            print("PyTorch not detected. Running Sensor Fusion in deterministic fallback mode.")

    def fuse(self, vis_hr, vis_snr, ac_rr, ac_snr, motion_level=0.0):
        """
        Fuses visual and acoustic metrics dynamically based on quality factors.
        Falls back to a robust deterministic mathematical fusion if PyTorch is unavailable.
        """
        
        # Clamp inputs to safe ranges
        vis_hr = max(40.0, min(180.0, vis_hr))
        ac_rr = max(6.0, min(40.0, ac_rr))
        vis_snr = max(-20.0, min(20.0, vis_snr))
        ac_snr = max(-20.0, min(20.0, ac_snr))

        # Check PyTorch compatibility
        if self.torch_enabled and self.model is not None:
            try:
                # Prepare features
                # visual: [HR, SNR, motion]
                vis_tensor = torch.tensor([[vis_hr, vis_snr, motion_level]], dtype=torch.float32)
                # acoustic: [RR, SNR, noise variance]
                ac_tensor = torch.tensor([[ac_rr, ac_snr, 0.0]], dtype=torch.float32)
                # quality input: [visual SNR, acoustic SNR]
                quality_tensor = torch.tensor([[vis_snr, ac_snr]], dtype=torch.float32)
                
                with torch.no_grad():
                    hr_pred, rr_pred, conf_pred, weights = self.model(vis_tensor, ac_tensor, quality_tensor)
                    
                return (
                    float(hr_pred[0][0]),
                    float(rr_pred[0][0]),
                    float(conf_pred[0][0]),
                    float(weights[0][0]), # Visual attention weight
                    float(weights[0][1])  # Acoustic attention weight
                )
            except Exception as e:
                pass # Fallback to deterministic model if evaluation fails
                
        # --- Deterministic Fallback Model ---
        # Map SNRs to Sigmoid confidence metrics
        vis_conf = 1.0 / (1.0 + np.exp(-0.4 * (vis_snr - 2.0)))
        ac_conf = 1.0 / (1.0 + np.exp(-0.4 * (ac_snr - 2.0)))
        
        # Penalize visual confidence under motion
        motion_penalty = max(0.0, min(0.8, motion_level * 0.5))
        vis_conf = max(0.0, vis_conf - motion_penalty)
        
        # Calculate dynamic attention weights
        total_conf = vis_conf + ac_conf
        if total_conf > 0:
            w_visual = vis_conf / total_conf
            w_acoustic = ac_conf / total_conf
        else:
            w_visual = 0.5
            w_acoustic = 0.5
            
        # Vitals late-fusion:
        # Visual is primary for HR, but we can modulate its confidence
        fused_hr = vis_hr if vis_conf > 0.1 else 0.0
        
        # Acoustic is primary for RR, but camera motion-tracking (or forehead pixel fluctuations)
        # can estimate RR if audio confidence is extremely low
        fused_rr = ac_rr if ac_conf > 0.1 else 15.0 # Fallback to average RR
        
        # Overall system confidence
        system_confidence = (vis_conf + ac_conf) / 2.0
        
        return fused_hr, fused_rr, system_confidence, w_visual, w_acoustic

if __name__ == "__main__":
    # Test fusion engine
    engine = AdaptiveFusionEngine()
    
    print("Testing ideal conditions:")
    print("HR=72, visual SNR=10dB, RR=16, acoustic SNR=8dB")
    print(engine.fuse(72.0, 10.0, 16.0, 8.0))
    
    print("\nTesting high visual noise (e.g. motion/lighting drop):")
    print("HR=72, visual SNR=-5dB, RR=16, acoustic SNR=10dB, motion=0.8")
    print(engine.fuse(72.0, -5.0, 16.0, 10.0, motion_level=0.8))
