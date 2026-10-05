import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import os

FIG_DIR = "/workspace/papers/sci_affective_safety_calibration/submission_pack_v0_4/figures"
os.makedirs(FIG_DIR, exist_ok=True)

plt.rcParams.update({
    'font.family': 'serif',
    'font.size': 10,
    'axes.linewidth': 0.8,
    'figure.dpi': 300,
    'savefig.dpi': 300,
    'savefig.bbox': 'tight',
    'text.usetex': False,
})

fig, ax = plt.subplots(1, 1, figsize=(7, 4))
ax.set_xlim(0, 10)
ax.set_ylim(0, 6)
ax.axis('off')

boxes = [
    (1.0, 4.0, 2.5, 1.2, 'Cognitive\nAppraisal\nVector'),
    (4.0, 4.0, 2.5, 1.2, 'Affective\nMemory\nModule'),
    (7.0, 4.0, 2.5, 1.2, 'Hesitation\nPolicy'),
]
for x, y, w, h, label in boxes:
    rect = mpatches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.1",
                                    facecolor='white', edgecolor='black', linewidth=1.2)
    ax.add_patch(rect)
    ax.text(x + w/2, y + h/2, label, ha='center', va='center', fontsize=9, fontweight='bold')

sub_boxes = [
    (0.5, 1.5, 1.8, 1.0, 'Controllable\nvs Irreversible'),
    (2.5, 1.5, 1.8, 1.0, 'Internal\nvs External'),
    (4.5, 1.5, 1.8, 1.0, 'Severity-\nWeighted\nTraces'),
    (6.5, 1.5, 1.8, 1.0, 'Similarity\nGeneralization'),
    (8.5, 1.5, 1.2, 1.0, 'Auto /\nSim /\nReview /\nBlock'),
]
for x, y, w, h, label in sub_boxes:
    rect = mpatches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.05",
                                    facecolor='#f0f0f0', edgecolor='black', linewidth=0.8)
    ax.add_patch(rect)
    ax.text(x + w/2, y + h/2, label, ha='center', va='center', fontsize=7)

ax.annotate('', xy=(4.0, 4.6), xytext=(3.5, 4.6),
            arrowprops=dict(arrowstyle='->', lw=1.2))
ax.annotate('', xy=(7.0, 4.6), xytext=(6.5, 4.6),
            arrowprops=dict(arrowstyle='->', lw=1.2))
ax.annotate('', xy=(1.4, 2.5), xytext=(2.25, 4.0),
            arrowprops=dict(arrowstyle='->', lw=0.8, ls='--'))
ax.annotate('', xy=(3.4, 2.5), xytext=(2.25, 4.0),
            arrowprops=dict(arrowstyle='->', lw=0.8, ls='--'))
ax.annotate('', xy=(5.4, 2.5), xytext=(5.25, 4.0),
            arrowprops=dict(arrowstyle='->', lw=0.8, ls='--'))
ax.annotate('', xy=(7.4, 2.5), xytext=(5.25, 4.0),
            arrowprops=dict(arrowstyle='->', lw=0.8, ls='--'))
ax.annotate('', xy=(9.1, 2.5), xytext=(8.25, 4.0),
            arrowprops=dict(arrowstyle='->', lw=0.8, ls='--'))

ax.set_title('Figure 1: Affective Safety Calibration Framework', fontsize=11, fontweight='bold', pad=10)
fig.savefig(os.path.join(FIG_DIR, 'fig1_framework_architecture.png'))
fig.savefig(os.path.join(FIG_DIR, 'fig1_framework_architecture.pdf'))
plt.close(fig)
print("Fig 1 done")

fig, ax = plt.subplots(1, 1, figsize=(6, 5))
ax.set_xlim(0, 10)
ax.set_ylim(0, 8)
ax.axis('off')

tiers = [
    (1.5, 5.5, 7, 1.5, 'Tier 1: Auto-Execute', 'LOW risk\nRead-only, safe checks', '#e8f5e9'),
    (1.5, 3.5, 7, 1.5, 'Tier 2: Simulate-First', 'MEDIUM risk\nDry-run, preview required', '#fff3e0'),
    (1.5, 1.5, 7, 1.5, 'Tier 3: Human-Review / Block', 'HIGH / CRITICAL risk\nHuman approval or block', '#ffebee'),
]
for x, y, w, h, title, desc, color in tiers:
    rect = mpatches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.1",
                                    facecolor=color, edgecolor='black', linewidth=1.2)
    ax.add_patch(rect)
    ax.text(x + 0.3, y + h - 0.3, title, fontsize=10, fontweight='bold', va='top')
    ax.text(x + 0.3, y + 0.3, desc, fontsize=8, va='bottom', color='#333333')

ax.annotate('', xy=(5, 5.5), xytext=(5, 5.0),
            arrowprops=dict(arrowstyle='->', lw=1.5))
ax.annotate('', xy=(5, 3.5), xytext=(5, 3.0),
            arrowprops=dict(arrowstyle='->', lw=1.5))

ax.annotate('Threshold adjusted\nby Affective Memory', xy=(9, 4.25),
            fontsize=8, fontstyle='italic', ha='center', va='center',
            bbox=dict(boxstyle='round', facecolor='#e3f2fd', edgecolor='gray', linewidth=0.8))

ax.set_title('Figure 2: Three-Tier Safety Decision Policy', fontsize=11, fontweight='bold', pad=10)
fig.savefig(os.path.join(FIG_DIR, 'fig2_three_tier_policy.png'))
fig.savefig(os.path.join(FIG_DIR, 'fig2_three_tier_policy.pdf'))
plt.close(fig)
print("Fig 2 done")

fig, ax = plt.subplots(1, 1, figsize=(7, 4))

methods = ['SafeKeyword\nFirstBaseline', 'KeywordRule\nBaseline', 'RiskContext\nOracle*', 'FullCalibrator\nAdapter', 'DeepSeek-v4-flash\nJudge (aux.)']
values = [0.872, 0.780, 0.064, 0.036, 0.000]
colors = ['#d32f2f', '#f44336', '#ff9800', '#388e3c', '#1565c0']

bars = ax.bar(methods, values, color=colors, edgecolor='black', linewidth=0.8, width=0.6)

for bar, val in zip(bars, values):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
            f'{val:.3f}', ha='center', va='bottom', fontsize=9, fontweight='bold')

ax.set_ylabel('Risky Auto-Execution Rate', fontsize=10)
ax.set_ylim(0, 1.0)
ax.axhline(y=0.05, color='gray', linestyle='--', linewidth=0.8, label='5% threshold')
ax.legend(fontsize=8, loc='upper right')
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)

ax.set_title('Figure 3: Risky Auto-Execution Rate Comparison', fontsize=11, fontweight='bold', pad=10)

footnote = '*Oracle is non-deployable diagnostic reference.\nDeepSeek result on auxiliary AffectiveBenchmark-300 stress set, not Semi-Real-300.'
ax.text(0.5, -0.18, footnote, transform=ax.transAxes, fontsize=7, ha='center', va='top', fontstyle='italic')

fig.savefig(os.path.join(FIG_DIR, 'fig3_risky_auto_exec_comparison.png'))
fig.savefig(os.path.join(FIG_DIR, 'fig3_risky_auto_exec_comparison.pdf'))
plt.close(fig)
print("Fig 3 done")

fig, ax = plt.subplots(1, 1, figsize=(6, 4))

episodes = np.arange(1, 11)
no_memory = np.full(10, 0.043)
single_failure = np.array([0.043]*3 + [0.036]*7)
accumulated = np.array([0.043, 0.043, 0.036, 0.036, 0.018, 0.012, 0.006, 0.003, 0.001, 0.000])

ax.plot(episodes, no_memory, 'o--', color='#d32f2f', label='No memory (0.043)', linewidth=1.5, markersize=5)
ax.plot(episodes, single_failure, 's--', color='#ff9800', label='Single failure (->0.036)', linewidth=1.5, markersize=5)
ax.plot(episodes, accumulated, '^-', color='#388e3c', label='Accumulated (->0.000)', linewidth=1.5, markersize=5)

ax.set_xlabel('Episode', fontsize=10)
ax.set_ylabel('Risky Auto-Execution Rate', fontsize=10)
ax.set_ylim(-0.005, 0.06)
ax.legend(fontsize=8, loc='upper right')
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
ax.set_xticks(episodes)

ax.set_title('Figure 4: Longitudinal Memory Tradeoff', fontsize=11, fontweight='bold', pad=10)
fig.savefig(os.path.join(FIG_DIR, 'fig4_longitudinal_memory_tradeoff.png'))
fig.savefig(os.path.join(FIG_DIR, 'fig4_longitudinal_memory_tradeoff.pdf'))
plt.close(fig)
print("Fig 4 done")

print("\nAll 4 figures generated (PNG + PDF) in:", FIG_DIR)
