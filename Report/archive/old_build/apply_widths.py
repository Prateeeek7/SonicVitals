with open('test_build.tex', 'r') as f:
    text = f.read()

# 1. Update dashboard_main to figure* with \textwidth
p_dash_start = text.find(r'\begin{figure}[!t]' + '\n' + r'    \centering' + '\n' + r'    \includegraphics[width=\columnwidth]{images/dashboard_main.png}')
p_dash_end = text.find(r'\end{figure}', p_dash_start) + len(r'\end{figure}')
assert p_dash_start != -1 and p_dash_end != -1, "dashboard_main block not found"

new_dash_block = r'''\begin{figure*}[!t]
    \centering
    \includegraphics[width=\textwidth]{images/dashboard_main.png}
    \caption{Real-time clinical monitoring dashboard of the proposed SonicVitals platform, displaying the live patient camera stream with full-face tracking HUD, vital telemetry metrics (HR: 72\,BPM, RR: 16\,breaths/min, HRV: 58\,ms, $\mathrm{SpO_2}$: 98\%, Stress Index: 36\%), Signal Quality Index (94\%), system status (STABLE), and diagnostic capture controls.}
    \label{fig:dashboard_main}
\end{figure*}'''

text = text[:p_dash_start] + new_dash_block + text[p_dash_end:]

# 2. Update signal_analysis_dashboard to width=\textwidth
text = text.replace(r'\includegraphics[width=0.92\textwidth, height=4.4cm, keepaspectratio]{images/signal_analysis_dashboard.png}',
                    r'\includegraphics[width=\textwidth]{images/signal_analysis_dashboard.png}')

# 3. Update acoustic_group to single-column figure with \columnwidth
p_ac_start = text.find(r'\begin{figure*}[!t]' + '\n' + r'    \centering' + '\n' + r'    \begin{minipage}{0.48\textwidth}' + '\n' + r'        \centering' + '\n' + r'        \includegraphics[width=\columnwidth, height=2.8cm, keepaspectratio]{images/acoustic_input.png}')
p_ac_end = text.find(r'\end{figure*}', p_ac_start) + len(r'\end{figure*}')
assert p_ac_start != -1 and p_ac_end != -1, "acoustic_group block not found"

new_ac_block = r'''\begin{figure}[!t]
    \centering
    \includegraphics[width=\columnwidth]{images/acoustic_input.png}\\[0.2ex]
    {\footnotesize (a) Raw 16\,kHz I2S thoracic acoustic phonocardiogram ($S_1, S_2$).}\\[0.8ex]
    \includegraphics[width=\columnwidth]{images/spectrogram_audio.png}\\[0.2ex]
    {\footnotesize (b) 512-point STFT acoustic time-frequency spectrogram.}\\[0.2ex]
    \caption{Acoustic phonocardiography and time-frequency auscultation processing: (a) High-fidelity 16\,kHz I2S thoracic audio stream captured by the INMP441 MEMS microphone showing phonocardiographic heart sound impulses ($S_1, S_2$), and (b) corresponding 512-point STFT spectrogram resolving valvular closure transients below 150\,Hz and vesicular respiratory acoustics up to 1.2\,kHz.}
    \label{fig:acoustic_group}
\end{figure}'''

text = text[:p_ac_start] + new_ac_block + text[p_ac_end:]

# 4. Update optical_group to single-column figure with \columnwidth
p_op_start = text.find(r'\begin{figure*}[!t]' + '\n' + r'    \centering' + '\n' + r'    \begin{minipage}{0.32\textwidth}' + '\n' + r'        \centering' + '\n' + r'        \includegraphics[width=\columnwidth, height=2.5cm, keepaspectratio]{images/mcn_traces.png}')
p_op_end = text.find(r'\end{figure*}', p_op_start) + len(r'\end{figure*}')
assert p_op_start != -1 and p_op_end != -1, "optical_group block not found"

new_op_block = r'''\begin{figure}[!t]
    \centering
    \includegraphics[width=\columnwidth]{images/mcn_traces.png}\\[0.1ex]
    {\footnotesize (a) MCN RGB color traces.}\\[0.6ex]
    \includegraphics[width=\columnwidth]{images/rbvp_pulse.png}\\[0.1ex]
    {\footnotesize (b) Reconstructed BVP pulse.}\\[0.6ex]
    \includegraphics[width=\columnwidth]{images/rsw_respiration.png}\\[0.1ex]
    {\footnotesize (c) Respiration RSW waveform.}\\[0.6ex]
    \includegraphics[width=\columnwidth]{images/mrwd_wavelet.png}\\[0.1ex]
    {\footnotesize (d) Multi-Resolution Wavelet Decomposition ($A_3, D_1, D_2$).}\\[0.6ex]
    \includegraphics[width=\columnwidth]{images/fft_spectrum.png}\\[0.1ex]
    {\footnotesize (e) Welch PSD periodogram ($f_{peak} = 1.20$\,Hz).}\\[0.2ex]
    \caption{Optical rPPG decomposition, wavelet multi-resolution denoising, and frequency-domain spectral analysis: (a) Motion-compensated normalized color signals, (b) reconstructed BVP waveform with sharp systolic peaks and visible dicrotic notch, (c) isolated respiratory modulation trace at 16.0\,breaths/min, (d) multi-resolution wavelet sub-bands separating baseline drift ($A_3$) from hemodynamic details ($D_2$) and sensor noise ($D_1$), and (e) Welch PSD periodogram identifying the dominant cardiac fundamental frequency at $1.20$\,Hz with an in-band SNR of 14.8\,dB.}
    \label{fig:optical_group}
\end{figure}'''

text = text[:p_op_start] + new_op_block + text[p_op_end:]

# 5. Save updated file
with open('test_build.tex', 'w') as f:
    f.write(text)

print('apply_graph_and_dashboard_widths.py completed successfully.')
