# Forgetting, decay and surprise in cognitive science and in AI-agent memory

Research note A for Plexus (FalkorDB graph memory for agent teams). Scope: what cognitive science says about forgetting, decay and salience, how published agent-memory work implements it, and what was measured. Every external claim carries a ledger citation [n]; `[unverified]` marks claims from model knowledge or my own inference. Numbers marked "computed here" are my arithmetic on a published formula, not a reported result.

Reading guide: Part 1 is cognitive science, Part 2 is AI papers, Part 3 is the evidence on whether decay helps or hurts, Part 4 is Implications for Plexus.

---

## Part 1. Cognitive science

### 1.1 The Ebbinghaus forgetting curve and its replications

Ebbinghaus measured retention by "savings" (the reduction in repetitions needed to relearn a list). The values quoted in a UCSC ACT-R lecture are 58.2% savings at 0.33 h, 44.2% at 1 h, 35.8% at 8.8 h, 33.7% at 24 h, 27.8% at 48 h, 25.4% at 144 h and 21.1% at 744 h.[8] That is a steep initial drop followed by a long flat tail.

Murre & Dros (2015) replicated the experiment with one subject who spent 70 hours learning and relearning lists at 20 min, 1 h, 9 h, 1 d, 2 d and 31 d.[9] They report that the results are similar to Ebbinghaus's original data and that the curve "most probably shows a jump upwards starting at the 24 hour data point".[9] They compared the replication with Ebbinghaus's data and with an earlier replication by Mack and Seitz, and found the normalised curves strikingly alike.[9]

Functional form matters for Plexus. Ebbinghaus himself fitted a power function and later a logarithmic one.[9] Wixted's review states that a variety of empirical forgetting functions are accurately described by both the power and logarithmic functions (with a slight edge to the power law) and "very poorly described by the exponential".[10] Exponential decay, `R = e^(-t/S)`, is nonetheless what several agent papers call "the Ebbinghaus curve" (see MemoryBank and FadeMem below).[2][33]

Why a power law at all: Anderson & Schooler argued that memory behaves as if it made a statistical inference from the past history of use to the probability that an item is needed now.[24] On this "rational analysis" view, the forgetting curve mirrors how the need probability of items in the environment falls off.[24] That is the theoretical bridge to ACT-R below.

### 1.2 Spacing and retrieval practice (testing effect)

- **Testing effect.** Roediger & Karpicke (2006): students studied prose passages and then either took free-recall tests or restudied. On a 5-minute final test restudying was better. On 2-day and 1-week tests "prior testing produced substantially greater retention than studying", even though restudying raised confidence.[12] Retrieval is itself a memory-strengthening event, not only a read-out.
- **Spacing.** Cepeda et al.'s 2006 meta-analysis covers 839 assessments of distributed practice in 317 experiments in 184 articles, examining spacing, lag and expanding intervals.[13] A later large study found that the best gap depends on the retention interval; the authors of that paper summarise an earlier study in which a 1-month gap was best for a 6-month retention interval, implying a gap-to-retention ratio of roughly 15-20% if optimum gap scaled linearly (they warn linearity cannot be assumed).[28]
- **Why spacing works in an activation model.** Pavlik & Anderson (2005) model each practice as an increment of strength that decays as a power function of time, where "the rate of decay for each presentation depended on the activation at the time of the presentation". This limits the long-term benefit of further practice at high activation and yields the spacing effect.[11] The agent-side analogue is diminishing returns on repeated reads that happen close together.

### 1.3 ACT-R base-level activation (the equation)

ACT-R gives each declarative chunk an activation `A = B + (context terms) + noise`. In the form used by Honda & Fujita, `A(m) = B(m) + Σ_j W_j·S_j + ε`, where ε is Gaussian noise.[32] The base-level term is

```
B_i = ln( Σ_{k=1..n} t_k^(-d) )          t_k = time since the k-th use of chunk i,  d = decay (usually 0.5)
```

The same equation is stated in the UCSC lecture, which notes that with `d = 0.5` it reduces to `ln Σ 1/√t_k`.[8] Honda & Fujita define it identically and describe `d` as "a decay parameter (typically around 0.5)", giving frequency and recency in one number: recently and frequently used memories stay accessible and the rest decay.[32] Petrov's ICCM paper describes the same structure as "a logarithm of a sum of powers": each new use adds a term that then decays independently with rate `d`, producing a sharp transient peak after each use, decay without use, and gradual accretion with frequent use.[29]

How frequency and recency combine: each use contributes `t^-0.5` independently, so they add before the log. A single recent use can outrank several old ones, and many spread-out uses outrank one. Numbers below are **computed here** from the equation with `t` in seconds, `d = 0.5`:

| History | B (computed here) | vs 1 access 1 day ago |
|---|---|---|
| 1 access, 1 h ago | -4.09 | +1.59 |
| 1 access, 1 d ago | -5.68 | 0 |
| 1 access, 7 d ago | -6.66 | -0.97 |
| 1 access, 30 d ago | -7.38 | -1.70 |
| 1 access, 90 d ago | -7.93 | -2.25 |
| 5 accesses at 1, 3, 7, 14, 30 d ago | -4.81 | +0.88 |
| 5 accesses in a burst 60 d ago | -6.12 | -0.44 |
| 10 weekly accesses, last 1 d ago | -4.68 | +1.00 |

Under power-law decay the weight of a use 30 days old is `30^-0.5 ≈ 0.18` of a use 1 day old (computed here), a fat tail. An exponential with the Generative Agents constant (0.995 per hour) would give 0.03 for the same pair (computed here). The difference is exactly the "rarely used but critical" fact problem discussed in Part 3.

Cost and approximation: the exact equation needs every access timestamp, which Petrov calls "very expensive to compute" at scale, and ACT-R's community uses an approximation that keeps only the count and the chunk's age: `B ≈ ln[ n/(1-d) · t_n^(-d) ]`, optionally combined with exact terms for the k most recent uses.[29] (The extracted PDF garbles the symbols; the form is as I read it and should be checked against the paper before coding.) For Plexus this matters little, because the graph already stores timestamped READ and RETURNED edges, so the exact sum is cheap. [unverified: that it is cheap in FalkorDB at scale; benchmark before relying on it.]

Soar's forgetting work uses the same quantity as a deletion criterion. Derbinsky & Laird forget "knowledge that is not in active use (as determined by base-level activation) and can likely be reconstructed if it becomes relevant", and report improved reactivity and scaling while maintaining reasoning competence in a robotics simulation and a multi-player game.[22] The "can be reconstructed" condition is the safety rule that matters for Plexus.

### 1.4 Interference versus decay, and retrieval-induced forgetting

- **Decay vs interference.** Wixted recounts that Jenkins & Dallenbach (1924) found more recall after sleep than after waking: interference theory predicts less forgetting during sleep, decay theory predicts no difference, so "decay theory was essentially abandoned".[10] Wixted's own review argues for interference plus consolidation, and notes the power law of forgetting and Jost's law imply older memories decay more slowly than younger ones of equal strength.[10] The sources I read do not settle the debate, so for an engineered index it is safest to treat time decay as a modelling convenience rather than a mechanism.
- **Retrieval-induced forgetting (RIF).** Anderson, Bjork & Bjork (1994): after repeated retrieval practice of some category members, unpracticed members of the same category were recalled worse on a delayed test, which the authors interpret as retrieval-based suppression lasting 20 minutes or more; the impairment was restricted to high-frequency members.[14] So retrieving one memory can actively weaken its competitors.
- **Storage strength vs retrieval strength.** Bjork & Bjork's "new theory of disuse" gives each item two strengths: storage strength (how well learned) and retrieval strength (current ease of access). Recall depends only on retrieval strength, and items with high storage strength can have low retrieval strength (a phone number from 20 years ago).[30] This is the cleanest cognitive justification for "forgetting as ranking, not deletion".
- **Forgetting as a feature.** Richards & Frankland argue that transience enhances flexibility by reducing the influence of outdated information on decisions, and prevents overfitting to specific past events.[25]

### 1.5 Emotional salience, surprise and novelty

- **Von Restorff / isolation effect.** If all but one item of a list are similar on some dimension, memory for the different item is enhanced; Hunt's review says modern theory emphasises perceptual salience and the differential attention it draws.[15]
- **Novelty and dopamine.** Lisman & Grace propose a hippocampal-VTA loop: the hippocampus detects information not already in long-term memory, the novelty signal reaches VTA dopamine cells (together with salience and goal information), and dopamine released in the hippocampus enhances LTP and learning, so the loop "regulates the entry of information into long-term memory".[17]
- **Emotion and consolidation.** McGaugh's review: the amygdala (basolateral complex) mediates the memory-modulating effects of stress hormones and neuromodulators and is critical for retaining lasting memories of emotional experiences; the effect is on consolidation.[27]
- **Prediction error drives encoding.** Greve et al. tested one-shot learning of a new scene-face pairing: memory was better when the erroneous prior was more precise (larger prediction error), and the reaction-time slow-down at the critical trial (a proxy for prediction error) correlated with associative memory.[16] Sinclair et al. (fMRI): prediction error, produced by interrupting narrative videos before the expected ending, reversed the relationship between hippocampal activation and memory, so activation predicted preservation after expected endings but memory *updating* after surprising endings; the authors conclude that prediction errors "create conditions that favor memory updating".[23] Surprise therefore strengthens the new trace and also makes the old one malleable.
- **Flashbulb memories: accuracy caveat.** Talarico & Rubin followed 54 students after 9/11; consistency of flashbulb and everyday memories did not differ and both declined, but vividness, recollection and belief in accuracy declined only for everyday memories. Their conclusion: "Flashbulb memories are not special in their accuracy, as previously claimed, but only in their perceived accuracy".[18] A ten-year follow-up (Hirst et al.) found rapid forgetting in the first year then levelling off, with confidence remaining high throughout; inconsistent flashbulb memories were more likely to be repeated than corrected.[19]

Take-away for design: surprise/emotion raises *priority and confidence*, not *truth*. A salience boost must not be read as a correctness signal.

---

## Part 2. AI agent memory papers

Formulas are quoted as published. Where the PDF text extraction dropped Greek symbols, I describe the symbol in words.

### 2.1 Generative Agents (Park et al., UIST 2023)

- **Mechanism.** A memory stream of natural-language records. Retrieval combines three terms.[1]
- **Recency.** "an exponential decay function over the number of sandbox game hours since the memory was last retrieved. Our decay factor is 0.995."[1] Note it is *since last retrieval*, so each retrieval resets the clock. Half-life from `0.995^h = 0.5` is about 138 game hours (about 5.8 days) (computed here).
- **Importance.** An integer from 1 to 10 elicited from the LLM at creation time ("1 is purely mundane ... 10 is extremely poignant"). Examples: "cleaning up the room" returns 2, "asking your crush out on a date" returns 8.[1] This is a salience score, but it is LLM-judged on content, not a measured surprise.
- **Relevance.** Cosine similarity between the embedding of the memory and of the query.[1]
- **Combination.** "we normalize the recency, relevance, and importance scores to the range of [0, 1] using min-max scaling" and score = α_recency·recency + α_importance·importance + α_relevance·relevance, with "all α's set to 1".[1] Top-ranked memories that fit the context window go into the prompt.[1] Reflection triggers when the summed importance of recent events exceeds 150.[1]
- **What was evaluated.** Believability, ranked by 100 participants and converted to TrueSkill. Full architecture 29.89 (σ 0.72); no reflection 26.88; no reflection or planning 25.64; crowdworker 22.95; no memory/planning/reflection 21.21.[1] The ablations disabled access to *memory types* (observation, reflection, planning) rather than individual scoring terms, so the paper does not isolate the effect of the recency decay or the importance term.[1] The authors' own future-work section proposes tuning the three functions.[1]

### 2.2 MemoryBank (Zhong et al., 2023)

- **Mechanism.** Ebbinghaus-inspired memory updating for the SiliconFriend companion.[2] `R = e^(-t/S)`, R retention, t time since learning, S memory strength "modeled as a discrete value" initialised to 1 on first mention; when a memory is recalled, "We increase S by 1 and reset t to 0".[2] The paper calls this "an exploratory and highly simplified memory updating model".[2]
- **Rationale given.** Forgetting "less important memory pieces that are long time ago and have not been recalled much can make the AI companion more natural".[2] The motivation is anthropomorphism, not retrieval accuracy.
- **Evaluated.** 3 SiliconFriend variants scored on retrieval accuracy, response correctness, coherence and ranking, with ChatGPT simulating users.[2] The paper claims applicability "with and without memory forgetting mechanism" but its quantitative table compares models and languages, not forgetting on versus off, so I found **no measured effect of the forgetting rule itself**.[2]

### 2.3 Titans (Behrouz et al., Google, 2025)

- **Mechanism.** A neural long-term memory that learns at test time. "an event that violates the expectations (being surprising) is more memorable", and surprise is the gradient of the associative-memory loss with respect to the input.[3] Loss: `ℓ(M_{t-1}; x_t) = ||M_{t-1}(k_t) − v_t||²`.[3]
- **Surprise with momentum.** `S_t = η_t·S_{t-1} − θ_t·∇ℓ(M_{t-1}; x_t)`, where the first term is "past surprise" and the second is "momentary surprise"; η_t is "data-dependent surprise decay" and θ_t scales how much momentary surprise is incorporated.[3] The motivation is that an event can stay memorable after the initial surprise has faded.[3]
- **Forgetting gate.** `M_t = (1 − α_t)·M_{t-1} + S_t` with α_t ∈ [0,1]: α→0 leaves memory untouched, α→1 clears it; the paper shows this is weight decay and generalises the gates in modern recurrent models.[3] The stated purpose is managing limited capacity at very long sequence length.[3]
- **Measured effect.** Ablation (Table 5): without weight decay perplexity worsens from 27.01 to 29.04, reasoning accuracy falls from 47.83 to 45.11, and the long-context score from 92.68 to 85.60; the paper says the greatest contribution comes from weight decay, then momentum, convolution and persistent memory.[3]
- **Caveat for Plexus.** This is a decay in the weights of a fixed-capacity parametric memory under a training objective. It is not time-based decay of discrete records. The transferable idea is that surprise (error against the current model) gates writing, and forgetting is relative to capacity.

### 2.4 EM-LLM (Fountas et al., ICLR 2025)

- **Mechanism.** Surprise-based *event segmentation*, not forgetting. A token is a boundary if `−log P(x_t | x_1..x_{t-1}) > T`, where the threshold T is derived from the mean and variance of surprise over a moving window with scaling factor γ.[4] Boundaries are then refined with graph-theoretic modularity or conductance, and events are retrieved by similarity plus temporal contiguity.[4]
- **Evaluated.** LongBench and ∞-Bench. EM-LLM improves on InfLLM across 5 base LLMs and beats RAG on a wide range of tasks, and retrieves across 10 million tokens.[4]
- **Relevance.** Surprise is used to decide *what unit to store*, and nothing is forgotten; the paper lists consolidation against catastrophic forgetting only as future work.[4] It needs token log-probabilities from an LM, which Plexus does not have.

### 2.5 A-MEM (Xu et al., 2025)

- **Mechanism.** Zettelkasten-style notes with LLM-generated links, and "memory evolution" where new memories trigger updates to existing notes' context and tags.[5] The evolution prompt offers actions "strengthen", "merge", "prune".[5]
- **Forgetting.** None as a time-based mechanism; I found no decay term in the paper. Evaluated on LoCoMo against LoCoMo, ReadAgent, MemoryBank and MemGPT baselines in F1 and BLEU-1 over six foundation models.[5]

### 2.6 MemGPT / Letta (Packer et al., 2023)

- **Mechanism.** OS-style virtual context management. A FIFO queue holds recent messages; when prompt tokens exceed the warning count (e.g. 70% of context) the model is warned, and at the flush count (e.g. 100%) the queue manager "evicts a specific count of messages (e.g. 50% of the context window), generates a new recursive summary", while evicted messages remain in recall storage.[6]
- **Nature of forgetting.** Capacity-driven eviction plus lossy summarisation, never access- or time-weighted decay.[6] Evaluated on deep memory retrieval and document analysis.[6]

### 2.7 MemoryAgentBench (Hu et al., 2025) and "selective forgetting"

- **What it defines.** Four competencies: accurate retrieval, test-time learning, long-range understanding and selective forgetting. Selective Forgetting (SF) is "The skill to revise, overwrite, or remove previously stored information when faced with contradictory evidence", tied to model editing and unlearning.[7] It is **not** passive decay.
- **Dataset.** FactConsolidation (single-hop and multi-hop), where later facts contradict earlier ones.[7]
- **Result.** "all methods fail on the multi-hop situation (with achieving at most 28% accuracy)"; only long-context agents do reasonably on single-hop.[7] A stronger reasoning model improves matters but "Selective Forgetting still poses a significant challenge to all memory mechanisms"; in the validation table (as I read the column layout) multi-hop FactConsolidation at 32K tokens is 10% for GPT-4o and 14% for o4-mini.[7]
- **Why it matters here.** The benchmark's notion of forgetting is exactly what Plexus's SUPERSEDES edges and validity windows implement by construction. It also means that *decay is not what is being tested*.

### 2.8 Other published memory systems with decay or heat

- **MemoryOS (2025).** Segment "Heat = N_visit + L_interaction + R_recency" as a weighted sum, where N_visit counts retrievals, L_interaction is the number of dialogue pages in the segment and R_recency is an exponential decay in the time since last retrieval (decay constant not legible in my extraction); heat decides segment deletion and promotion to long-term persona memory.[41]
- **FadeMem (Wei et al., Jan 2026).** Dual-layer memory with strength `v(t) = v(0)·exp(−λ_i·(t − τ_i)^β_i)`, `λ_i = λ_base·exp(−γ·I_i(t))`, β = 0.8 for the long-term layer and 1.2 for the short-term layer; at importance 0 and λ_base = 0.1 the half-lives are about 11.25 days and 5.02 days.[33] Importance `I = α·relevance + β·(saturating function of access count) + γ·exp(−Δt)`; each access adds `Δv·(1−v)·exp(−n/N)` (diminishing returns); memories are pruned below a strength threshold or after T_max dormant days.[33] Conflicts are resolved by an LLM and newer information suppresses older with `v·exp(−λ·clip(Δt/W,0,1))`.[33] Evaluated on Multi-Session Chat, LoCoMo and an author-built LTI-Bench: 82.1% retention of critical facts at 55.0% storage versus Mem0 78.4% at 100%, LoCoMo multi-hop F1 29.43 versus Mem0 28.37 and MemGPT 9.46, 45% storage reduction.[33] The ablations remove the dual layer, fusion and conflict resolution, not decay alone.[33]
- **Oblivion (Rana et al., Apr 2026).** Frames forgetting "as decay-driven reductions in accessibility — not explicit deletion".[34] Retention `R_t(c) = exp(−n_t(c)/S_t(c))` per memory cluster, where n_t is turns since last access, `S_t = U_t + F_t + ε` combines a learned utility proxy and an access-frequency proxy, scaled by a decay temperature T; reinforcement is applied only to memories that contributed to the response.[34] Reported results: outperforms direct and memory baselines on LongMemEval and GoodAI LTM, with up to 73% token-cost reduction at 120K interaction spans.[34] Sensitivity to T: low T (1, 3) decays so fast that retention goes to near zero, T = 10 balances, T = 50 saturates the buffer and recreates always-on retrieval; the optimum "remains task- and capacity-dependent".[34]
- **ScrubJay-MEM (2026).** Per-memory, type-conditioned decay `U = V·exp(−λ_i·…)` where the decay coefficient comes from an auto-classified type: stable factual λ of 0.05-0.15 (horizon weeks-months), procedural 0.20-0.40 (days-weeks), task-specific 0.50-0.70 (hours-days), ephemeral 0.80-1.00 (minutes-hours); the type is assigned by an LLM-prompt classifier with a keyword fallback.[37]
- **Human-inspired memory architecture (Microsoft, May 2026).** Passive decay `I(t) = I0·e^(−λt)` with λ = 0.001 per hour (half-life about 29 days); interference-based forgetting `Σ_j w_j·sim(m_i, m_j)` with retroactive weight 0.6 and proactive 0.4; and graceful degradation through fidelity levels from full record to gist to a tombstone that keeps only the fact that a memory existed.[43]
- **CAMeR (2026).** Weight update `w ← γ·w` (γ = 0.99 per round) when not activated, `min(1, w + 0.2)` when activated by a keyword-gated hybrid match; promotion to a slower decay (0.995) after 50 activations.[38]
- **MemTier (2026).** Time-decay signal `e^(−λt)` with λ = 0.05 per day (half-life about 14 days, t = age in days), combined linearly with BM25, cognitive-weight and tier signals (default weights 0.35 BM25, 0.25 decay, 0.25 cognitive weight, 0.15 tier); a **decay-bypass rule** sets the decay signal to 1 when the raw BM25 score exceeds 2.0, so a strong lexical match overrides the recency penalty.[39]
- **FSFM (China Mobile, 2026).** Taxonomy of passive decay, active deletion, safety-triggered and reinforcement-based forgetting; importance score is a weighted sum with a -10 penalty for dangerous content and -2 for sensitive content; prunes 10% of lowest-scoring records when over capacity.[35]

---

## Part 3. Does decay help or hurt? What was measured

I looked for ablations that isolate *time decay* from everything else. They are rare. Summary, with the claim each supports:

| Paper | Measurement | Reading |
|---|---|---|
| Titans [3] | Removing the weight-decay forgetting gate worsens perplexity 27.01 → 29.04 and long-context score 92.68 → 85.60 | Helps, but it is capacity management in parametric memory |
| MemTier [39] | Removing the time-decay signal changes LongMemEval-S accuracy 0.382 → 0.394 (+0.012); removing two-stage scoping drops it to 0.342 | Decay neutral to slightly negative; the authors attribute flat ablations to BM25 dominating the weights |
| ZenBrain [42] | NoDecay counterfactual: P@5 difference 0.002 (Cohen's d 0.015), "within measurement noise" | Decay is retrieval-neutral at moderate load; synthetic corpora |
| ScrubJay-MEM [37] | A decay ablation collapses the Generalization Gap by 5.7 on the authors' temporal test; but decay "suppresses the very memories the task requires" on MemoryAgentBench FactConsolidation | Helps for perishable facts, hurts when stale facts must stay visible |
| CAMeR [38] | The keyword gate, "not learnable decay", is the primary performance driver; time-driven baselines (Oblivion, SuperLocalMemory) reportedly collapse to near-zero weights over 100 rounds | Pure time decay is fragile; benchmark is 76 memories, synthetic |
| FadeMem [33] | Higher critical-fact retention at 55% storage; ablations do not isolate decay | Efficiency win, causal role of decay unproven |
| Oblivion [34] | Up to 73% token reduction; T mis-set either collapses retention or saturates the buffer | Efficiency win, sensitive to one hyperparameter |
| FSFM [35] | Preserves 70% of high-value content while pruning to capacity; claims +8.49% access efficiency and +29.2% signal-to-noise | Explicit loss of 30% of high-value content; single-company data |
| MemoryBank [2], Generative Agents [1] | Forgetting rule / scoring terms not ablated | No evidence either way |

Further evidence from four sources:

1. **Decay can erase facts that a later step needs.** ScrubJay-MEM's authors state that on FactConsolidation, where "factual updates supersede earlier statements but stale facts must remain visible for the consolidation step", their perishability mechanism is "actively miscalibrated".[37] MemoryAgentBench's own multi-hop selective-forgetting scores (at most 28%) show how hard conflict handling already is without any decay layer.[7]
2. **Rarely used but critical facts.** FSFM's own results admit a 30% loss of high-value business content under capacity pruning.[35] The Oblivion sensitivity study shows near-zero retention at low T.[34] I found **no paper that directly measures the loss of rarely-used-but-critical facts** as a named outcome. [unverified: that none exists; my searches covered arXiv titles and snippets for 2025-2026 only.]
3. **Deletion helps only with a reliable utility signal.** Xiong et al. found periodical deletion gives large memory reduction with small performance loss, and that history-based (utility) deletion improves agent performance when the evaluator is strict, but with a coarse or noisy evaluator history-based deletion can degrade performance.[31] Their central finding is error propagation: past inaccurate records compound and hurt later tasks.[31]
4. **Write-time curation beats read-time filtering in one setting.** Zahn & Chana gate writes on a composite salience score (source reputation, novelty, reliability), keep version chains that preserve prior states, and report that at 8:1 distractor ratios read-time filtering (Self-RAG) collapses to 0% while write gating stays at 100%.[40] Synthetic and LLM-judged, but the design principle ("archives rather than deletes superseded information") matches Plexus.[40]

Interaction effects: ZenBrain reports "cooperative masking": under moderate load fourteen of fifteen ablations look costless, but raising decay to 0.25/day over 60 days makes nine of the fifteen individually critical.[42] So ablation results at low load understate how much the surrounding machinery matters once decay is aggressive.

Honest bottom line from the sources: published evidence supports decay mainly as an **efficiency and noise-control** mechanism (fewer tokens, smaller stores), with **neutral** effects on accuracy in the two cleanest ablations (MemTier, ZenBrain).[39][42] Effects are **negative** where stale or old facts are required (ScrubJay on FactConsolidation, FSFM's 30% loss).[37][35] Most 2026 papers are single-lab, self-built benchmarks, and several evaluate with LLM judges, so effect sizes should be treated as indicative.

---

## Part 4. Implications for Plexus

Plexus already records the raw ingredients that these papers have to bolt on: READ edges (a Step consumed a fact), RETURNED edges with rank and score (a Recall surfaced a fact), `valid_from/valid_to`, SUPERSEDES/CONTRADICTS, provenance, and a `Fact.status` set that already contains `forgotten` (docs/graph-model.md). No LLM is needed to compute activation from these.

### 4.1 Forgetting as ranking, not deletion

Recommendation: **model forgetting as a decaying retrieval score on the default "what do I know now?" ranking, never as removal of nodes or history.**

- Bjork's split gives the principle: keep storage strength (node, validity window, provenance) forever and modulate only retrieval strength.[30]
- Oblivion makes the same design choice explicitly ("not explicit deletion"), keeping traces latent but reactivatable.[34]
- Deletion is justified only for reconstructable items: Derbinsky & Laird forget only what "can likely be reconstructed".[22] In Plexus, facts DERIVED_FROM source code are reconstructable (re-derive from the repo); human decisions and handoffs are not. Reconstructability can be an eligibility flag for the deepest tier (`status = forgotten` as an archival tombstone, in the style of the fidelity ladder in [43]).
- **As-of queries and history must ignore activation.** MemoryAgentBench's selective-forgetting task and ScrubJay's failure show stale facts must stay visible for consolidation.[7][37] Activation should apply only to default current-state recall, and SUPERSEDES/valid_to should remain the sole mechanism that changes what is *true*.
- Wixted's review favours interference plus consolidation over pure clock-time decay as the cause of ordinary forgetting.[10] [Inference, not a sourced claim: a database does not degrade with age, so Plexus's SUPERSEDES edges are interference resolution made explicit; time decay is only a way to reduce ranking noise.]

### 4.2 Which formula to adopt

Recommendation: **ACT-R base-level activation with `d = 0.5`, computed from READ edges (and discounted RETURNED edges), added to semantic relevance with a small weight; plus a salience-driven initial boost.**

Why this one:
- It is the only candidate with a decades-long fit to human data and an explicit frequency+recency combination.[24][29] Power-law decay matches empirical forgetting functions where exponential fits "very poorly".[10]
- It needs no per-fact hyperparameter beyond `d`, unlike FadeMem (λ_base, β per layer, γ, thresholds) or Oblivion (T tuned per capacity).[33][34]
- It has direct precedent in the agent literature in the same combined form `A = B + w·cos + noise`.[32] (Honda & Fujita evaluated this by simulation of memory behaviour, not by task accuracy, so it is not evidence that accuracy improves.[32])
- It is a rank score, so it composes with the vector search Plexus already does.

Concrete proposal (design, not a sourced result):

```
B(f, now) = ln( Σ_k w_k · (now − t_k)^(-0.5) )     over t_0 = recorded_at (the write) and every READ / RETURNED of f
score     = cosine_sim(query, f)  +  β · squash(B)  [+ optional ε noise for exploration]
```

- `w_k`: 1.0 for a READ by a Step that goes on to WRITE (the agent used it), smaller for a bare RETURNED. Reason: Oblivion reinforces only memories "contributing to forming the response", and counting every surfacing creates a rich-get-richer loop where what is ranked high is returned more and thus ranked higher.[34] [Loop risk is my inference.]
- `squash`/`β`: B is a log in seconds, with differences of 1-2 nats between a day and a month (table in 1.3), so unscaled it would swamp cosine similarity. Generative Agents min-max-normalise each term to [0,1] and weight them equally.[1] Start there, then tune β on Plexus's own recall logs.
- **Relevance bypass.** MemTier's rule that a strong lexical match overrides the recency penalty avoids burying an exactly-matching but old fact.[39] Equivalent for Plexus: exact subject_id+predicate hits, or cosine above a high threshold, ignore B.
- **Spacing/diminishing returns.** Reads packed into one burst should count less than spread-out reads. The Pavlik-Anderson activation-dependent decay formalises this[11] but I did not retrieve its parameter values, so treat it as optional v2; a cheap proxy is FadeMem's `exp(−n/N)` saturation over a sliding window.[33]
- **Alternative considered.** FSRS, the open-source spaced-repetition scheduler, uses a power-form curve `R(t,S) = (1 + factor·t/S)^(−w20)` with `factor = 0.9^(−1/w20) − 1` so that retrievability is 90% when t = S, and a trainable decay exponent (FSRS-6).[26] It needs per-item stability and difficulty fitted from review grades, which Plexus does not have, so ACT-R's count-and-timestamp form is the better fit. [Fit judgement is mine.]
- **Cost.** If exact sums over edges are too slow, store `n` and first-access time and use the count-based approximation, with exact terms for the most recent few reads.[29]
- Reject: MemoryBank's `e^(−t/S)` with integer S (it fits human forgetting poorly and was never ablated).[2][10] Reject Generative Agents' 0.995/hour as-is: the constant is tied to a 2-day simulation and gives a 5.8-day half-life, so a 30-day-old fact is down-weighted about 33× relative to a 1-day-old one, versus about 5.5× under d = 0.5 (computed here).[1] Its useful ideas are decay since *last retrieval* and min-max combination.[1]

### 4.3 Surprise and salience without an LLM

Plexus has local embeddings and graph structure, not token probabilities, so EM-LLM's `−log P` and Titans' gradient surprise are not directly available.[3][4] Deterministic proxies grounded in the science:

1. **Contradiction/supersession as prediction error.** A write that SUPERSEDES or CONTRADICTS an active fact is a literal violation of the store's expectation; Sinclair et al. show such surprise promotes updating and malleability of the old memory.[23] Boost the new fact's initial activation; mark the old one for faster rank decay (its validity already ends).
2. **Embedding novelty.** `1 − max cosine` to existing facts on the same subject or scope. This mirrors the hippocampal novelty signal[17] and the isolation effect.[15] Greve et al. found that more precisely-predicted-then-violated associations are better encoded, so novelty relative to a *confident* neighbour should weigh more than novelty in an empty region.[16]
3. **Outcome surprise.** A failed test, build or tool call following the use of a fact. [Design suggestion; no source retrieved for agents.]

Implement as `m` pseudo-accesses at creation time (`m = 1 + κ·salience`), so one formula covers recency, frequency and salience, in the spirit of FadeMem's importance-modulated decay rate and MemoryBank's strength increments.[33][2] Cap the boost. Caveats from the science: flashbulb-type salience inflates *confidence*, not accuracy.[18][19] Keep salience separate from `confidence` and from validity. Surprising writes can also be wrong or malicious, so write-time gating on source reliability is worth borrowing.[40]

### 4.4 Interaction with the staleness / re-verification feature

These are different axes and should stay separate:

- **Activation** = how easily a fact is surfaced (Bjork's retrieval strength).[30]
- **Validity/staleness** = whether the fact is still true (Plexus's valid_to, plus "suspect when the code it describes changes").

Rules that follow:
1. **Never let activation outrank staleness.** A fact flagged suspect should be down-ranked or annotated in answers regardless of how often it was read. (Rich-get-richer risk: frequently read facts are exactly the ones whose staleness hurts most.) [Inference.]
2. **Do not let reads of a suspect fact reinforce it** until it is re-verified, otherwise stale facts accumulate activation.
3. **Re-verification is a retrieval-plus-test event.** The testing effect says successful retrieval practice strengthens memory more than passive re-exposure.[12] Record a verification as a high-weight access, which resets the recency clock.
4. **Avoid "stale and forgotten".** A fact that has faded to low activation and then becomes stale is the worst case: nothing surfaces it for review. Use a separate *review ranking* in which the staleness flag (a code change is a prediction-error-like event[23]) raises priority for verification while the *answer ranking* penalises it.
5. **Selective-forgetting benchmark logic applies.** Superseded or stale-flagged facts must remain retrievable for consolidation and audit.[7][37]

### 4.5 Risks

| Risk | Evidence / reasoning |
|---|---|
| Critical rarely-used facts (constraints, security rules, decisions) sink | FSFM loses 30% of high-value content under pruning[35]; Oblivion shows near-zero retention at low T[34]; no paper measures it directly (above). Mitigate: importance class floors, pins, reconstructability gate, power-law tail, relevance bypass[39][22] |
| Decay hurts tasks that need stale or superseded facts | ScrubJay on FactConsolidation[37]; MemoryAgentBench SF[7]. Keep as-of queries activation-free |
| Self-reinforcing ranking loop from counting RETURNED | Oblivion reinforces only response-contributing memories[34]; loop risk is [unverified] inference |
| Salience mistaken for truth | Flashbulb findings[18][19] |
| Hyperparameter fragility | Oblivion's optimum T is task- and capacity-dependent[34]; ACT-R's `d` has a conventional default[32] |
| Weak evidence base | Decay ablations are neutral on accuracy in cleaner tests[39][42]; many 2026 results are single-lab and use LLM judges |
| Multi-agent effects | None of the cited work studies shared memory across agents; whether one agent's reads should refresh another's view is an open design choice [unverified] |
| RIF-style competitor suppression | Cognitively real[14] but not recommended: it would silently demote siblings that SUPERSEDES/CONTRADICTS already model explicitly |

### 4.6 Suggested evaluation before shipping

Plexus can test what the papers could not: a decay-on / decay-off A/B on its own recall logs, with outcome measures of (a) recall of known-critical but rarely-read facts, (b) rank of current vs superseded facts, (c) token/byte cost, (d) time to detect staleness. Use MemoryAgentBench FactConsolidation[7] and LongMemEval-style temporal and knowledge-update questions as external checks, and report the ablation that the surveyed papers mostly omit: ranking with and without the activation term, holding everything else fixed.

### 4.7 Coverage gaps

- I did not retrieve the full text of Anderson & Lebiere's ACT-R book or the ACT-R reference manual; the equation is sourced from a lecture note, a conference paper and an agent paper that restate it.[8][29][32] ACT-R's retrieval-probability and activation-noise formulas are not sourced here; `P(retrieve) = 1/(1+e^{-(A-τ)/s})` is from memory. [unverified]
- Several PDF equations lost Greek symbols in extraction (FadeMem, Oblivion, ScrubJay, Petrov); I describe the structure and give only constants I could read. Check the original papers before copying formulas into code.
- Mem0, Zep and Letta production systems were not reviewed beyond MemGPT's paper.
- Cepeda 2006 was read at abstract level only.[13]

## Sources

[1] https://arxiv.org/pdf/2304.03442 — Generative Agents: Interactive Simulacra of Human Behavior (Park et al. 2023)
[2] https://arxiv.org/pdf/2305.10250 — MemoryBank: Enhancing LLMs with Long-Term Memory (Zhong et al.)
[3] https://arxiv.org/pdf/2501.00663 — Titans: Learning to Memorize at Test Time (Behrouz et al. 2025)
[4] https://arxiv.org/pdf/2407.09450 — Human-inspired Episodic Memory for Infinite Context LLMs (EM-LLM)
[5] https://arxiv.org/pdf/2502.12110 — A-MEM: Agentic Memory for LLM Agents
[6] https://arxiv.org/pdf/2310.08560 — MemGPT: Towards LLMs as Operating Systems
[7] https://arxiv.org/pdf/2507.05257 — Evaluating Memory in LLM Agents via Incremental Multi-Turn Interactions (MemoryAgentBench)
[8] https://people.ucsc.edu/~abrsvn/ACT-R_subsymbolic_3.pdf — Intro to the ACT-R subsymbolic level for declarative memory (Brasoveanu, UCSC)
[9] http://journals.plos.org/plosone/article?id=10.1371/journal.pone.0120644 — Murre & Dros (2015) Replication and Analysis of Ebbinghaus' Forgetting Curve, PLOS ONE
[10] https://wixtedlab.ucsd.edu/publications/wixted/AnnualReview.pdf — Wixted (2004) The Psychology and Neuroscience of Forgetting, Annu. Rev. Psychol.
[11] https://pubmed.ncbi.nlm.nih.gov/21702785 — Pavlik & Anderson (2005) Practice and forgetting effects on vocabulary memory (PubMed)
[12] https://pubmed.ncbi.nlm.nih.gov/16507066 — Roediger & Karpicke (2006) Test-enhanced learning, Psychol Sci
[13] https://digitalcommons.usf.edu/psy_facpub/1771 — Cepeda et al. (2006) Distributed practice in verbal recall tasks: review and quantitative synthesis
[14] https://psycnet.apa.org/fulltext/1995-04358-001.html — Anderson, Bjork & Bjork (1994) Remembering can cause forgetting
[15] https://pubmed.ncbi.nlm.nih.gov/24203592 — Hunt (1995) The subtlety of distinctiveness: what von Restorff really did
[16] https://pubmed.ncbi.nlm.nih.gov/28579691 — Greve et al. (2017) Does prediction error drive one-shot declarative learning?
[17] https://pubmed.ncbi.nlm.nih.gov/15924857 — Lisman & Grace (2005) The hippocampal-VTA loop
[18] https://homepage.villanova.edu/diego.fernandezduque/Teaching/CognitivePsychology/Lectures_and_Labs/s6LongTermMemory/FlashbulbMemory/Talarico%20&%20Rubin%202003.pdf — Talarico & Rubin (2003) Confidence, not consistency, characterizes flashbulb memories
[19] https://nyuscholars.nyu.edu/en/publications/a-ten-year-follow-up-of-a-study-of-memory-for-the-attack-of-septe — Hirst et al. (2015) Ten-year follow-up of memory for 9/11
[22] https://derbinsky.info/_custom/files/research/publications/csr2013/paper.pdf — Derbinsky & Laird (2013) Effective and efficient forgetting of learned knowledge in Soar's working and procedural memories
[23] https://pubmed.ncbi.nlm.nih.gov/34911768 — Sinclair et al. (2021) Prediction errors disrupt hippocampal representations and update episodic memories (PubMed abstract)
[24] https://users.cs.northwestern.edu/~paritosh/papers/KIP/AndersonSchooler1991ReflectionsOfEnvironmentOnMemory.pdf — Anderson & Schooler (1991) Reflections of the environment in memory
[25] https://pubmed.ncbi.nlm.nih.gov/28641107 — Richards & Frankland (2017) The persistence and transience of memory, Neuron
[26] https://github.com/open-spaced-repetition/awesome-fsrs/wiki/The-Algorithm/5bf70e459e45152d40988c670fa7c4625b5e8577 — FSRS: The Algorithm (open-spaced-repetition wiki)
[27] https://pubmed.ncbi.nlm.nih.gov/15217324 — McGaugh (2004) The amygdala modulates the consolidation of memories of emotionally arousing experiences
[28] https://laplab.ucsd.edu/articles/Cepeda%20et%20al%202008_psychsci.pdf — Cepeda et al. (2008) Spacing effects in learning: a temporal ridgeline of optimal retention
[29] https://act-r.psy.cmu.edu/wordpress/wp-content/uploads/2012/12/652petrovAbstract.pdf — Petrov (2006) Computationally efficient approximation of the base-level learning equation in ACT-R
[30] https://andymatuschak.org/prompts/Bjork1992.pdf — Bjork & Bjork (1992) A new theory of disuse (PDF mirror)
[31] https://arxiv.org/pdf/2505.16067 — How Memory Management Impacts LLM Agents: experience-following (Xiong et al. 2025)
[32] https://dl.acm.org/doi/full/10.1145/3765766.3765803 — Honda & Fujita (2025) Human-Like Remembering and Forgetting in LLM Agents: An ACT-R-Inspired Memory Architecture (HAI 25)
[33] https://arxiv.org/pdf/2601.18642 — FadeMem: Biologically-Inspired Forgetting for Efficient Agent Memory (Wei et al. 2026)
[34] https://arxiv.org/pdf/2604.00131 — OBLIVION: Self-Adaptive Agentic Memory Control through Decay-Driven Activation (Rana et al. 2026)
[35] https://arxiv.org/pdf/2604.20300 — FSFM: A Biologically-Inspired Framework for Selective Forgetting of Agent Memory (2026)
[37] https://arxiv.org/pdf/2608.04746 — Caching for the Future: Scrub Jay Episodic Memory Principles for Agent Memory Systems (ScrubJay-MEM)
[38] https://arxiv.org/pdf/2607.20458 — CAMeR: Keyword-Gated Hybrid Activation for Adaptive Memory Retention in LLM Agents
[39] https://arxiv.org/pdf/2605.03675 — MemTier: Tiered Memory Architecture and the Retrieval Bottleneck in Long-Running LLM Agents
[40] https://arxiv.org/pdf/2603.15994 — Selective Memory for AI: Write-Time Gating with Hierarchical Archiving (Zahn & Chana 2026)
[41] https://arxiv.org/pdf/2506.06326 — Memory OS of AI Agent (Kang et al. 2025)
[42] https://arxiv.org/pdf/2604.23878 — ZenBrain: A Neuroscience-Inspired 7-Layer Memory Architecture (Bering 2026)
[43] https://arxiv.org/pdf/2605.08538 — Human-Inspired Memory Architecture for LLM Agents (Kerestecioglu et al., Microsoft 2026)
