López-Herrera et al. Discover Artificial Intelligence (2025) 5:224 Discover Artificial Intelligence
https://doi.org/10.1007/s44163-025-00424-4
RESEARCH Open Access
Directional forecasting for eight forex pairs
against the US dollar using machine learning
techniques
Francisco López-Herrera1, Jaime González Maiz Jiménez2* and Adán Reyes Santiago3
*Correspondence:
Jaime González Maiz Jiménez Abstract
jaime.gonzalezmaiz@udlap.mx This paper evaluates machine learning (ML) algorithms for forex trading based
1Research, Universidad Nacional
on directional forecasting over the 2018–2023 period. We conduct a rigorous
Autónoma de México, Mexico City,
Mexico comparative analysis of seven ML techniques—Logistic Regression, Decision Trees,
2Finance and Accounting, Random Forest, Gradient Boosting, AdaBoost, XGBoost, and Neural Networks—
Universidad de Las Américas
across eight currency pairs against the US dollar, including major (EUR, JPY, CHF,
Puebla, Puebla, Mexico
3EGADE Business School Sede AUD), managed float (CNY), and emerging market (MXN, ZAR, TRY) currencies. Our
Monterrey, Instituto Tecnológico methodology implements comprehensive hyperparameter optimization through
y de Estudios Superiores de
time series cross-validation, realistic dynamic transaction costs based on institutional
Monterrey, Moterrey, Mexico
spreads, and extends evaluation to future validation periods. Uniquely, we compare
traditional accuracy-based optimization with the profit-aware Mean Absolute
Directional Loss (MADL) function for model selection for the Logistic Regression
model. Results demonstrate that simpler, interpretable models achieve superior
risk-adjusted returns, with Logistic Regression optimized using MADL obtaining the
highest Risk-Adjusted Performance Index (RAPI) scores of 1.45–1.58. All ML strategies
show statistical significance after multiple testing corrections (Hansen’s SPA test,
t-statistics: 2.96–2.89), with medium to large economic effect sizes (Cohen’s d: 0.47–
0.60). However, performance varies dramatically with transaction costs—while major
pairs remain profitable with round-trip costs below 0.4%, emerging market currencies
become unviable at institutional spreads exceeding 1.0%. Value-at-Risk backtesting
reveals that ML models calibrated for directional prediction fail catastrophically for
risk estimation (29.1% average violations versus 5% expected), mandating separate
risk management frameworks. Our findings challenge the complexity bias in financial
ML, demonstrating that interpretable models with proper profit-aware optimization
outperform black-box approaches in real-world trading conditions. Clinical trial
number: not applicable.
Keywords Machine learning, Directional forecasting, Forex forecasting, Feature
engineering, Transaction costs, MADL, Interpretability, Value-at-risk
JEL Classification C53, C58, F31, G17
© The Author(s) 2025. Open Access This article is licensed under a Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International
License, which permits any non-commercial use, sharing, distribution and reproduction in any medium or format, as long as you give appropriate
credit to the original author(s) and the source, provide a link to the Creative Commons licence, and indicate if you modified the licensed material.
You do not have permission under this licence to share adapted material derived from this article or parts of it. The images or other third party
material in this article are included in the article’s Creative Commons licence, unless indicated otherwise in a credit line to the material. If material
is not included in the article’s Creative Commons licence and your intended use is not permitted by statutory regulation or exceeds the permitted
use, you will need to obtain permission directly from the copyright holder. To view a copy of this licence, visit h t t p : / / c e r a t i v e c o m m o n .s o r g / l i c e n s
e s / b y - n c - n d / 4 . 0. /

López-Herrera et al. Discover Artificial Intelligence (2025) 5:224 Page 2 of 32
1 Introduction
The first two decades of the twenty-first century have witnessed unprecedented tech-
nological advancements, driven by cutting-edge digital technologies and applications in
Artificial Intelligence (AI). Bahoo et al. [2] argue that AI, as a branch of computer sci-
ence, creates intelligent machines capable of performing cognitive tasks such as reason-
ing, learning, decision-making, and pattern recognition, traditionally considered human
tasks.
The AI adoption in the financial sector has significantly intensified since 2015,
reflected in the growing number of research articles in this domain. According to Price-
waterhouse Coopers [27], AI solutions have permeated every major sector of the econ-
omy, profoundly transforming the financial industry.
Within financial markets, foreign exchange prediction represents a particularly chal-
lenging domain where AI applications show significant promise. As Yilmaz and Ara-
baci [32] highlight, fluctuations in exchange rates can have profound impacts on foreign
trade, capital flows, asset management, and broader economic activity. The unique char-
acteristics of the forex market present distinct challenges for prediction models, as high-
lighted by Dautel et al. [13]. These include the market’s short-term interdealer trading
focus, large fluctuations, and the difficulty of consistently outperforming random walk
processes, as noted by Alvarez-Diaz [1].
Our research tackles these challenges through a comprehensive evaluation of machine
learning techniques for directional forex forecasting, addressing critical gaps in exist-
ing literature. While previous studies have focused primarily on prediction accuracy,
we implement a holistic framework that incorporates realistic transaction costs, rigor-
ous statistical validation, and systematic evaluation across diverse market regimes. We
extend the traditional ML evaluation paradigm by implementing Michańków et al.’s [25]
Mean Absolute Directional Loss (MADL) function, which aligns model optimization
with actual trading profitability rather than mere classification accuracy. This profit-
aware approach represents a fundamental shift from conventional ML applications in
finance, where models optimized for statistical accuracy often fail to generate profitable
trading strategies after accounting for real-world frictions.
Our study makes several novel contributions to the literature. First, we conduct a
comprehensive comparison of ML algorithms for forex trading, evaluating seven dis-
tinct approaches across eight currency pairs representing developed, emerging, and
exotic markets. Second, we implement dynamic, currency-specific transaction costs that
reflect actual institutional trading conditions, revealing critical viability thresholds that
previous studies have overlooked. Third, we provide rigorous statistical validation using
multiple testing frameworks, including Hansen’s [18] Superior Predictive Ability test,
ensuring our results are not artifacts of data mining. Fourth, we demonstrate that sim-
pler, interpretable models—particularly logistic regression with MADL optimization—
consistently outperform complex architectures in risk-adjusted terms, challenging the
prevailing assumption that predictive power requires algorithmic sophistication. Finally,
we reveal the fundamental inadequacy of ML models calibrated for directional predic-
tion when applied to risk management tasks, with VaR violation rates averaging 29.1%
versus the expected 5%, mandating separate frameworks for alpha generation and risk
control.

López-Herrera et al. Discover Artificial Intelligence (2025) 5:224 Page 3 of 32
The remainder of this paper is organized as follows: Sect. 2 presents a detailed review
of relevant literature, Sect. 3 describes our methodology and data, with particular
emphasis on our novel future period validation framework, Sect. 4 presents our empiri-
cal findings across both test and future periods, and Sect. 5 concludes with implications
and suggestions for future research.
2 Related work
The evolution of machine learning applications in forex prediction has paralleled broader
developments in financial technology. Early research established the challenges of forex
prediction, with Alvarez-Diaz [1] demonstrating that traditional linear models struggle
to consistently outperform random walk processes due to the nonlinear and dynamic
nature of exchange rates. This limitation spurred exploration of alternative approaches,
particularly artificial neural networks (ANNs) and ensemble methods.
The foundation for modern forex prediction was laid by seminal studies in the early
2000s. Zhang and Berardi [33] pioneered the use of neural network ensembles for
exchange rate prediction, while Nag and Mitra [26] introduced genetically optimized
neural networks to improve forecasting accuracy. These early successes prompted
deeper investigation into neural network architectures, with Lisi and Schiavo [24] and
Dhamija and Bhalla [14] demonstrating ANNs’ superior ability to capture nonlinear pat-
terns in foreign exchange data. However, Qi and Wu [28] notably cautioned that ANNs
incorporating market fundamentals might not consistently outperform random walk
processes in out-of-sample forecasts.
The field advanced significantly with the emergence of ensemble methods. Lai et al.
[23] demonstrated that ensemble approaches often surpass individual ANNs in forecast-
ing accuracy. This finding catalyzed research into hybrid methodologies, with Bielecki
et al. [8] developing sophisticated hybrid neural systems. The effectiveness of these
approaches was further validated by Dunis et al. [15], who showed that neural architec-
tures consistently outperformed traditional benchmarks in EUR/USD trading.
Recent years have witnessed substantial methodological innovations. Galeshchuk [16]
provided important insights into the limitations of perceptrons in generating profitable
trading strategies, while Galeshchuk and Mukherjee [17] demonstrated improved pre-
diction accuracy using deep convolutional neural networks. Sun et al. [30] made a sig-
nificant contribution by introducing the AdaBoost-LSTM ensemble, establishing new
benchmarks for financial time series forecasting performance. In contrast, Chen et al.
[10] explored various complex neural network architectures for USD exchange rate pre-
diction, though their results suggested significant limitations. In contrast, Talaei Khoei
et al. [31], propose a balance between model performance and comprehensibility.
Contemporary research has expanded both the scope and sophistication of forex pre-
diction methods. Datta et al. [12] conducted a comprehensive analysis of 22 currencies
against the US dollar, finding that deep learning algorithms consistently outperform tra-
ditional models across standard metrics. Hao et al. [19] advanced the field by developing
a bi-level ensemble learning approach specifically designed for complex exchange rate
time series. Chasipanta and Sánchez-Pozo [9] contributed to this evolution by compar-
ing traditional ARIMA models with neural networks for EUR/USD forecasting, while
Khan et al. [21] innovatively combined phase space reconstruction with heuristic algo-
rithms to enhance prediction accuracy of GBP/USD and CAD/USD exchange rates. On

López-Herrera et al. Discover Artificial Intelligence (2025) 5:224 Page 4 of 32
the same token, parallel research streams have demonstrated the broader applicability of
machine learning in financial markets. Reyes and González Maiz Jiménez [29] showed
superior performance of machine learning portfolios compared to passive investment
strategies in equity markets, while achieved high accuracy rates in stock price prediction
using advanced filtering techniques.
Recent advances in neural network architectures for financial forecasting have
explored sophisticated approaches to improve prediction accuracy. Bieganowski and
Ślepaczuk [7] investigate supervised autoencoders with noise augmentation and triple
barrier labeling, demonstrating that while these complex architectures can boost strat-
egy effectiveness, excessive complexity (large bottleneck sizes) and noise can impair per-
formance. Their findings highlight the critical importance of precise parameter tuning,
a theme that resonates with our results showing that simpler, well-tuned models often
outperform complex architectures in practical forex trading applications.
This extensive body of research reveals several critical insights about machine learning
applications in forex prediction. First, the documented failure of traditional economet-
ric approaches to capture non-linear exchange rate dynamics [3, 24] has driven adop-
tion of increasingly sophisticated ML architectures. Second, while neural networks and
ensemble methods demonstrate superior predictive accuracy [17, 19, 23], their complex-
ity often comes at the cost of interpretability and computational efficiency. Third, most
studies optimize for forecast accuracy using traditional error metrics, potentially mis-
aligning model objectives with actual trading profitability—a critical limitation recently
addressed by Michańków et al. [25].
Despite these advances, critical gaps remain in the literature. Most notably, existing
research lacks comprehensive analysis of how transaction costs impact ML strategy
viability across different currency pairs, particularly for emerging markets with wider
spreads. Furthermore, the field requires systematic evaluation of whether increased
model complexity translates to superior risk-adjusted returns in real trading conditions.
The recent emphasis on interpretability [31] suggests a need to balance sophistication
with practical implementation constraints. The application of machine learning to cryp-
tocurrency markets has provided additional insights transferable to forex prediction.
Berger and Koubova [5] demonstrate that forecast combination techniques significantly
improve Bitcoin return predictions, achieving superior performance through ensemble
methods—a finding that reinforces our multi-model approach for forex markets.
Therefore, the main aim of this research is to conduct a rigorous comparative analysis
of machine learning techniques for directional forex forecasting, explicitly incorporating
realistic transaction costs and evaluating performance across diverse market conditions.
We address three specific objectives: (1) determine whether simpler, interpretable mod-
els can achieve good levels of risk-adjusted performance; (2) identify which currency
pairs remain profitable after accounting for institutional-level transaction costs; and (3)
assess model robustness across different market regimes including the COVID-19 crisis.
This approach ensures trading viability rather than merely statistical accuracy.

López-Herrera et al. Discover Artificial Intelligence (2025) 5:224 Page 5 of 32
3 Methods and data
3.1 Data description and exploratory analysis
3.1.1 Dataset overview
This study employs daily foreign exchange rate data for eight currency pairs against the
US Dollar, spanning from January 1, 2018, to December 31, 2023. The dataset encom-
passes 1565 trading days per currency pair on average, providing a comprehensive view
of forex market dynamics across diverse economic conditions. The selected currencies—
EUR/USD, CNY/USD, JPY/USD, AUD/USD, CHF/USD, MXN/USD, ZAR/USD and
TRY/USD—represent diverse economic regions and capture varying market behaviors.
Each observation includes Open, High, Low, and Close (OHLC) prices, enabling detailed
analysis of intraday volatility patterns and market microstructure effects.
The temporal scope of this study is particularly significant as it captures three distinct
market regimes: the pre-COVID period (2018–2019) characterized by relatively stable
market conditions and gradual monetary policy normalization; the COVID-era (2020–
2021) marked by unprecedented volatility and central bank interventions; and the post-
COVID period (2022–2023) defined by aggressive monetary tightening and geopolitical
tensions. This natural experiment in market dynamics provides an ideal setting for eval-
uating machine learning models' adaptability to regime changes.
3.2 Descriptive statistics and market characteristics
Table 1 presents comprehensive descriptive statistics for the currency pairs across the
full sample period. The data reveals substantial heterogeneity in return distributions and
risk characteristics across currencies. Annualized returns range from − 31.1% (TRY/
USD) to 3.2% (MXN/USD). The Turkish Lira’s dramatic depreciation reflects persistent
inflationary pressures and unconventional monetary policy, while the South African
Rand’s − 5.4% annualized return captures commodity markets weakness and domestic
political uncertainty.
Annualized volatilities span from 4.5% (CNY/USD) to 21.1% (TRY/USD). Nota-
bly, TRY/USD exhibits volatility nearly five times that of CNY/USD, while ZAR/USD’s
15.4% volatility is next. All currency pairs exhibit varying degrees of skewness (ranging
from − 0.63 to 0.52) and excess kurtosis (− 0.81 to 7.12), indicating fat-tailed distribu-
tions, characteristics that violate the normality assumptions underlying many traditional
econometric approaches.
The Jarque–Bera test decisively rejects normality for all currency pairs (p < 0.001), with
TRY/USD showing an extreme test statistic of 265,701, far exceeding other pairs. While
Augmented Dickey-Fuller tests confirm that price series are non-stationary. These find-
ings have direct implications for machine learning model design, suggesting the need
for robust loss functions and careful feature engineering to capture non-linear dynamics
and tail dependencies.
The Sharpe ratios reveal a stark risk-return trade-off hierarchy, with TRY/USD’s −
1.47 representing the worst risk-adjusted performance, while CHF/USD offers the best
risk/return profile with a quotient of 0.36. The price range analysis shows TRY/USD’s
extraordinary 184.5% range over the sample period, dwarfing even volatile emerging
markets like ZAR/USD (55.6%) and highlighting the extreme depreciation pressure on
the Turkish Lira.

López-Herrera et al. Discover Artificial Intelligence           (2025) 5:224  Page 6 of 32
Table 1 Comprehensive descriptive statistics for eight forex currency pairs against USD (2018–2023)
Currency Daily_Return_Mean_% Daily_Return_Std_% Annual_Return_% Annual_Volatility_%
| EUR/USD | 0.004    | 0.46 | -1.10  | 7.26  |     |
| ------- | -------- | ---- | ------ | ----- | --- |
| CNY/USD | -0.005   | 0.28 | -1.29  | 4.52  |     |
| JPY/USD | -0.013   | 0.53 | -3.27  | 8.36  |     |
| AUD/USD | -0.007   | 0.65 | -1.67  | 10.31 |     |
| CHF/USD | 0.010    | 0.46 | 2.64   | 7.25  |     |
| MXN/USD | 0.125    | 0.78 | 3.15   | 12.43 |     |
| ZAR/USD | -0.0.022 | 0.97 | -5.42  | 15.39 |     |
| TRY/USD | -0.123   | 1.33 | -31.08 | 21.10 |     |
Currency Sharpe_Ratio Price_Range_% Skewness Kurtosis JB_Statistic
| EUR/USD | -0.15 | 25.9  | 0.06  | 1.36  | 118.8***   |
| ------- | ----- | ----- | ----- | ----- | ---------- |
| CNY/USD | -0.29 | 15.8  | 0.19  | 3.45  | 778.6***   |
| JPY/USD | -0.39 | 37.1  | 0.52  | 7.12  | 3,349.5*** |
| AUD/USD | -0.16 | 33.5  | -0.17 | 2.40  | 378.2***   |
| CHF/USD | 0.36  | 19.7  | 0.37  | 2.59  | 467.7***   |
| MXN/USD | 0.25  | 40.2  | -0.63 | 3.08  | 716.1***   |
| ZAR/USD | -0.35 | 55.6  | 0.32  | -0.20 | 19.88***   |
| TRY/USD | -1.47 | 184.5 | 0.21  | -0.81 | 265,701*** |
This table presents key statistical properties of daily returns and price dynamics for currency pairs representing developed
markets (EUR, CHF), emerging markets (CNY, MXN, ZAR), commodity currencies (AUD), safe havens (JPY), and exotic
currencies (TRY). Daily returns are calculated as log differences and expressed as percentages, with annualized metrics
computed using standard √252 scaling for volatility and 252 trading days for returns. The Sharpe ratio assumes zero risk-
free rate for simplicity. Price Range represents the percentage difference between the highest and lowest exchange rate
within the sample period, indicating total currency movement. Statistical moments reveal departure from normality:
skewness ranges from − 0.63 (MXN) to 0.52 (JPY), while excess kurtosis varies from − 0.81 (TRY) to 7.12 (JPY), indicating
fat-tailed distributions. The Jarque–Bera test statistic confirms non-normality for all pairs at 1% significance (***), with TRY
showing extreme non-normality (JB = 265,701). Key findings include: (1) TRY exhibits catastrophic depreciation (− 31.1%
annually) with extreme volatility (21.1%), yielding the worst risk-adjusted returns (Sharpe = − 1.47); (2) CNY demonstrates
the lowest volatility (4.5%) reflecting managed float policies; (3) CHF offers the best risk-return profile (Sharpe = 0.36)
confirming safe-haven status; (4) Emerging market currencies (ZAR, TRY) show 3–5 × higher volatility than majors, critical
for transaction cost considerations and position sizing in ML trading strategies
3.3 Volatility dynamics and regime characteristics
Figure 1 illustrates the evolution of 20-day rolling volatility across currency pairs, reveal-
ing pronounced clustering and regime-dependent behavior. The COVID-19 period wit-
nessed volatility spikes exceeding 35% annualized for emerging market currencies like
(MXN/USD), while TRY/USD reached extraordinary levels above 90% during crises
peaks. Whilst ZAR/USD demonstrated a volatility around 25% during market stress
periods, reflecting its dual nature as both a commodity and emerging market proxy.
In contrast, EUR/USD showed a moderate increase of 15%, showing a stark difference
between emerging and developed markets in terms of risk.
Notably, autocorrelation patterns in volatility are ideally suited for tree-based ensem-
ble methods like Random Forest and XGBoost. While traditional econometric models
struggle with such persistence, gradient boosting algorithms (XGBoost, Gradient Boost-
ing) excel at capturing these complex temporal dependencies through their sequential
learning approach and ability to model residual patterns. In contrast, the regime-switch-
ing nature of volatility, clearly visible in Fig. 2, presents both challenges and opportuni-
ties for machine learning models. Tree-based methods (Random Forest, Decision Trees)
naturally partition the feature space, allowing them to identify distinct volatility regimes
without explicit regime labels. Meanwhile, Adaptive Boosting’s focus on misclassified
instances may prove particularly valuable during regime transitions, where traditional
models often fail.

López-Herrera et al. Discover Artificial Intelligence (2025) 5:224 Page 7 of 32
Fig. 1 Evolution of 20-Day Rolling Volatility Across Major and Emerging Market Currency Pairs (2018–2023). This
figure presents the temporal dynamics of realized volatility calculated using a 20-day rolling window of daily re-
turns (annualized using √252 scaling) for four representative currency pairs against the USD. Panel (a) shows EUR/
USD representing developed markets with relatively stable volatility ranging from 5-15% except during the March
2020 COVID shock. Panel (b) displays MXN/USD, an emerging market currency exhibiting higher baseline volatility
(10–20%) with pronounced spikes exceeding 35% during crisis periods. Panel (c) illustrates ZAR/USD demonstrat-
ing intermediate volatility levels (15–25%) with notable clustering during 2020–2021. Panel (d) reveals TRY/USD's
exceptional volatility profile, reaching extreme levels above 90% during multiple crisis episodes, reflecting severe
macroeconomic instability. The shaded areas indicate major market events: COVID-19 pandemic (March 2020),
Federal Reserve policy shifts (2022), and banking sector stress (March 2023). These patterns demonstrate hetero-
geneous responses to global shocks, with exotic currencies experiencing disproportionate volatility amplification
compared to major pairs, critical for ML model training and risk management calibration.
3.3.1 Target variable definition
The prediction task is formulated as a binary classification problem where the target
variable equals 1 if tomorrow’s close exceeds today’s open (Close {t + 1} > Open t), and
0 otherwise. This definition captures tradable directional movements with positions
entered at today’s open and evaluated at tomorrow’s close, representing a realistic trad-
ing scenario where a trader opens a position at market open and assesses profitability at
the next day’s close. This binary formulation simplifies the prediction task while main-
taining practical relevance for trend-following strategies.
3.4 Correlation dynamics and portfolio implications
The correlation structure among currency pairs exhibits time variation with signifi-
cant implications for portfolio-based trading strategies. Table 2 summarizes correlation
matrices across the three identified market regimes. During the pre-COVID period, the
average pairwise correlation was 0.37. Interestingly, correlations maintained a similar
level during the COVID crisis. However, it is worth noting that the correlation between
EUR/USD and JPY/USD increased from 0.34 pre-COVID to 0.53 during the crisis,
exemplifying flight-to-quality dynamics. Post-COVID correlations remain relatively sta-
ble at approximately 0.40, although TRY/USD shows lower correlation with other cur-
rency pairs, which can be explained by its exotic nature. Alternatively, ZAR/USD shows
moderate correlations with commodity currencies like AUD/USD (0.59 pre-COVID,
0.57 COVID-era, 0.63 post-COVID), confirming its dual role as both an emerging mar-
ket and commodity proxy.

López-Herrera et al. Discover Artificial Intelligence (2025) 5:224 Page 8 of 32
Fig. 2 Volatility regime classification using percentile-based thresholds for EUR/USD and CNY/USD (2018–2023).
This figure illustrates the identification of distinct volatility regimes using 20-day rolling volatility with regime
boundaries defined by historical percentiles. The top panel shows EUR/USD volatility with three regimes: Low
(green shading, below 10th percentile, <5.2% annualized), Normal (white, 10th–90th percentile, 5.2–12.8%), and
High (red shading, above 90th percentile, >12.8%). The bottom panel displays CNY/USD with corresponding re-
gimes at lower absolute levels: Low (<2.8%), Normal (2.8–6.5%), and High (>6.5%), reflecting managed exchange
rate policies. Regime transitions are marked by vertical lines showing dates when volatility crosses percentile
thresholds. EUR/USD exhibits 47 regime changes indicating free-floating dynamics, while CNY/USD shows only
23 transitions, demonstrating greater stability. The analysis reveals that both pairs spent approximately 20% of the
sample in extreme regimes (10% low, 10% high by construction), but with different clustering patterns—EUR/USD
shows rapid regime switching during crisis periods while CNY/USD maintains longer regime persistence. These
regime dynamics directly inform our ML feature engineering, as tree-based methods can naturally partition data
according to these volatility states without explicit regime labels.
3.4.1 Value at risk
Historical VaR analysis at the 95% confidence level reveals substantial risk heteroge-
neity across currency pairs. VaR ranges from − 0.46% (CNY/USD) to − 1.68% (ZAR/
USD), establishing a clear risk hierarchy: CNY/USD < CHF/USD < EUR/USD < JPY/
USD < AUD/USD < MXN/USD < TRY/USD < ZAR/USD. These findings suggest the need
for robust loss functions and position-sizing algorithms in ML models to account for the
non-normal, heavy-tailed loss distributions evident across all currency pairs.
3.4.2 Market microstructure and trading patterns
Analysis of intraday price ranges (High–Low) reveals systematic patterns relevant for
feature engineering. The average daily range varies from 0.32% (CNY/USD) to 1.60%
(ZAR/USD) and TRY/USD exhibiting 1.11% of daily High-Low range. The latter two
showing the highest ranges, a measure of market efficiency, which deteriorates particu-
larly during more volatile periods, suggesting increased noise, and therefore potential
opportunities for ML-based filtering techniques.

López-Herrera et al. Discover Artificial Intelligence           (2025) 5:224  Page 9 of 32
Table 2 Time-varying correlation structure of currency pairs across market regimes (2018–2023)
Pre-Covid Period
| EUR/USD      | CNY/USD JPY/USD | AUD/USD | CHF/USD MXN/USD | ZAR/USD TYR/USD |
| ------------ | --------------- | ------- | --------------- | --------------- |
| EUR/USD 1    | 0.28 0.33       | 0.61    | 0.70 0.36       | 0.42 0.19       |
| CNY/USD 0.28 | 1 -0.04         | 0.38    | 0.12 0.27       | 0.39 0.15       |
| JPY/USD 0.34 | -0.04 1         | 0.11    | 0.55 0.02       | 0.02 -0.048     |
| AUD/USD 0.61 | 0.38 0.11       | 1       | 0.35 0.45       | 0.59 0.24       |
| CHF/USD 0.70 | 0.12 0.55       | 0.35    | 1 0.17          | 0.20 0.05       |
| MXN/USD 0.36 | 0.27 0.02       | 0.45    | 0.17 1          | 0.51 0.28       |
| ZAR/USD 0.42 | 0.39 0.02       | 0.59    | 0.20 0.51       | 1 0.34          |
| TRY/USD 0.19 | 0.15 -0.05      | 0.24    | 0.05 0.28       | 0.34 1          |
COVID-Era
| EUR/USD      | CNY/USD JPY/USD | AUD/USD | CHF/USD MXN/USD | ZAR/USD TYR/USD |
| ------------ | --------------- | ------- | --------------- | --------------- |
| EUR/USD 1    | 0.33 0.53       | 0.57    | 0.84 0.29       | 0.31 0.07       |
| CNY/USD 0.33 | 1 0.16          | 0.40    | 0.32 0.25       | 0.28 0.12       |
| JPY/USD 0.53 | 0.16 1          | 0.21    | 0.59 0.02       | 0.01 -0.02      |
| AUD/USD 0.57 | 0.40 0.21       | 1       | 0.45 0.57       | 0.57 0.15       |
| CHF/USD 0.84 | 0.32 0.59       | 0.45    | 1 0.21          | 0.20 0.02       |
| MXN/USD 0.29 | 0.25 0.02       | 0.57    | 0.21 1          | 0.70 0.14       |
| ZAR/USD 0.31 | 0.28 0.01       | 0.57    | 0.20 0.70       | 1 0.83          |
| TYR/USD 0.07 | 0.12 -0.02      | 0.15    | 0.02 0.14       | 0.18 1          |
Post-Covid Period
| EUR/USD      | CNY/USD JPY/USD | AUD/USD | CHF/USD MXN/USD | ZAR/USD TYR/USD |
| ------------ | --------------- | ------- | --------------- | --------------- |
| EUR/USD 1    | 0.46 0.43       | 0.67    | 0.73 0.43       | 0.55 0.08       |
| CNY/USD 0.46 | 1 0.35          | 0.48    | 0.43 0.16       | 0.36 0.11       |
| JPY/USD 0.43 | 0.35 1          | 0.46    | 0.51 0.19       | 0.34 0.06       |
| AUD/USD 0.67 | 0.48 0.46       | 1       | 0.63 0.48       | 0.63 0.09       |
| CHF/USD 0.73 | 0.43 0.51       | 0.63    | 1 0.31          | 0.47 0.08       |
| MXN/USD 0.43 | 0.16 0.19       | 0.48    | 0.31 1          | 0.53 0.08       |
| ZAR/USD 0.55 | 0.36 0.34       | 0.63    | 0.49 0.53       | 1 0.04          |
| TRY/USD 0.08 | 0.11 0.06       | 0.09    | 0.08 0.08       | 0.04 1          |
Full period
| EUR/USD      | CNY/USD JPY/USD | AUD/USD | CHF/USD MXN/USD | ZAR/USD TYR/USD |
| ------------ | --------------- | ------- | --------------- | --------------- |
| EUR/USD 1    | 0.37 0.44       | 0.62    | 0.75 0.34       | 0.43 0.10       |
| CNY/USD 0.04 | 1 0.21          | 0.43    | 0.32 0.21       | 0.34 0.12       |
| JPY/USD 0.44 | 0.21 1          | 0.31    | 0.54 0.08       | 0.15 -0.01      |
| AUD/USD 0.62 | 0.43 0.31       | 1       | 0.51 0.50       | 0.58 0.15       |
| CHF/USD 0.75 | 0.32 0.54       | 0.51    | 1 0.22          | 0.30 0.04       |
| MXN/USD 0.34 | 0.21 0.08       | 0.50    | 0.22 1          | 0.59 0.17       |
| ZAR/USD 0.43 | 0.34 0.15       | 0.58    | 0.30 0.59       | 1 0.21          |
| TRY/USD 0.10 | 0.12 -0.01      | 0.15    | 0.04 0.18       | 0.21 1          |
This table presents Pearson correlation coefficients of daily returns between eight currency pairs during three distinct
market regimes and the full sample period. Pre-COVID period (Jan 2018–Feb 2020) represents normal market conditions
with moderate average pairwise correlation of 0.37. COVID-Era (Mar 2020–Dec 2021) captures crisis dynamics where flight-
to-quality effects manifest in increased EUR/USD-JPY/USD correlation (0.34 → 0.53) and stronger safe-haven clustering
(EUR-CHF: 0.70 → 0.84). Post-COVID period (Jan 2022–Dec 2023) shows correlation normalization with average correlation
of 0.40, though TRY/USD remains largely decoupled (correlations < 0.11) due to idiosyncratic domestic factors. Notable
patterns include: (1) Persistent commodity currency linkages (AUD-ZAR: 0.59–0.63 across all periods); (2) Managed float
behavior in CNY/USD showing moderate but stable correlations (0.28–0.46); (3) Crisis-induced correlation convergence for
major pairs while exotic currencies maintain independence; (4) Negative or near-zero correlations between JPY and risk
currencies (MXN, ZAR) confirming yen’s safe-haven role. The full period matrix (bottom panel) smooths regime-specific
effects, showing overall correlation structure used for portfolio construction. These time-varying correlations have direct
implications for ML models: higher correlations during crisis periods may reduce diversification benefits but could enhance
cross-currency feature learning, while the general correlation instability suggests ensemble methods may outperform
single models by capturing diverse correlation regimes

López-Herrera et al. Discover Artificial Intelligence (2025) 5:224 Page 10 of 32
3.4.3 Implications for machine learning model development
The exploratory analysis reveals several critical considerations for ML model develop-
ment in forex prediction. First, the pervasive non-normality and fat-tailed distributions
necessitate robust architectures capable of handling outliers without excessive influence
on parameter estimation. Second, the models must incorporate time-varying parameters
or attention mechanisms to adapt to changing market conditions.
3.5 Feature engineering
From a feature engineering perspective, we employ three fundamental price-based indi-
cators designed to capture key market dynamics in exchange rate markets: daily returns
capturing directional momentum, normalized high-low range as an intraday volatility
proxy, and opening gaps reflecting overnight information flow and market sentiment
shifts. Given the distinct behavior across market regimes documented in our analysis,
ensemble methods combining models trained on different subperiods may better cap-
ture the non-stationary nature of forex markets. The success of any ML approach will
likely depend on its ability to adapt to the regime changes, tail events, and complex
dependencies revealed in this exploratory analysis. This controlled experimental design,
detailed in Fig. 3, enables systematic evaluation of whether macroeconomic indicators
enhance predictive performance beyond the information contained in price-based tech-
nical features alone.
Figure 3 illustrates our comprehensive research workflow. As shown in the diagram,
we first optimize all seven machine learning algorithms using three engineered techni-
cal features, employing fivefold time series cross-validation with randomized search to
identify optimal hyperparameters. Subsequently, we augment this baseline feature set
with four macroeconomic indicators: 5-year and 13-week Treasury bill rates, as well as
the yield curve slope and daily changes. These macro indicators capture term structure
dynamics and interest rate momentum that theoretically influence exchange rate move-
ments through interest rate parity mechanisms.
3.6 Machine learning models
We employ seven diverse machine learning algorithms to capture different aspects of
forex price dynamics. Logistic Regression serves as our linear baseline, modeling the
log-odds of directional movements through a linear combination of features. Decision
Tree provides a non-parametric alternative that recursively partitions the feature space,
naturally capturing threshold-based trading rules without assuming linear relationships.
Random Forest extends decision trees through bootstrap aggregation, where multiple
trees vote on predictions, reducing individual tree variance while maintaining the abil-
ity to model non-linear patterns. The boosting family includes three variants: Gradient
Boosting sequentially adds weak learners to minimize prediction errors, with each tree
correcting its predecessors' mistakes; AdaBoost adaptively reweights training instances,
forcing subsequent models to focus on previously misclassified cases; and XGBoost, an
optimized gradient boosting implementation that adds computational efficiencies and
enhanced regularization capabilities. Finally, Neural Network (Multi-Layer Perceptron)
employs layers of interconnected neurons with non-linear activation functions, enabling
the learning of complex feature representations.

López-Herrera et al. Discover Artificial Intelligence (2025) 5:224 Page 11 of 32
Fig. 3 Comprehensive machine learning research workflow for forex directional prediction. This flowchart illus-
trates our complete experimental design for evaluating ML models in forex prediction across multiple market
regimes. The workflow begins with data ingestion (8 currency pairs, 2018–2023, 1,565 trading days) and branches
into two parallel feature engineering paths: (1) Technical-only features comprising daily returns, high-low range,
and opening gaps, and (2) Technical + Macro features augmenting the baseline with Treasury yield curve indica-
tors (5-year and 13-week rates, slope, daily changes). Seven ML algorithms—Logistic Regression, Decision Tree,
Random Forest, Gradient Boosting, AdaBoost, XGBoost, and Neural Network—are trained on each feature set. The
optimization process employs fivefold time series cross-validation with RandomizedSearchCV (10 iterations) to se-
lect hyperparameters while preserving temporal order. Uniquely, Logistic Regression is optimized using both stan-
dard accuracy and MADL (Mean Absolute Directional Loss) to compare classification-based versus profit-aware
model selection. The framework is applied independently to four time periods capturing distinct market regimes:
Pre-COVID (522 days), COVID-era (521 days), Post-COVID (522 days), and Full period (1,565 days). Final evaluation
on held-out test sets (25% of each period) includes performance metrics, statistical significance tests, and sensitiv-
ity analyses. This multi-period, dual-feature approach enables robust conclusions about ML effectiveness across
varying market conditions
This algorithmic diversity spans linear models, single trees, ensemble methods, and
neural architectures, ensuring our findings reflect consistent patterns rather than pecu-
liarities of any specific modeling approach. Each algorithm represents a different induc-
tive bias: linear assumptions, recursive partitioning, ensemble voting, sequential error
correction, and hierarchical feature learning.
3.6.1 Transaction costs implementation
3.6.1.1 Dynamic transaction cost structure To ensure realistic trading simulations, we
implemented a comprehensive dynamic transaction cost structure based on actual forex
market spreads. Transaction costs vary by currency pair, reflecting their liquidity and
market characteristics. Major currency pairs (EUR/USD, JPY/USD, AUD/USD, CHF/
USD) are assigned spreads ranging from 1.2 to 2.5 pips, while emerging market curren-
cies (MXN/USD, ZAR/USD, TRY/USD) incur wider spreads of 3.0 to 8.0 pips, consis-
tent with typical institutional trading costs—See Table 3. The pip value for each currency
pair is configured based on market conventions: standard 4-decimal pairs (EUR/USD,
AUD/USD, CHF/USD, CNY/USD) use 0.0001, while JPY pairs use 0.00001 due to their

López-Herrera et al. Discover Artificial Intelligence (2025) 5:224 Page 12 of 32
Table 3 Transaction cost structure by currency pair
Currency pair Spread (pips) Pip value Price range* Cost range (%)** Round-trip range**
EUR/USD 1.2 0.0001 1.00–1.20 0.010–0.012 0.02–0.024
JPY/USD 1.5 0.00001 0.008–0.010 0.150–0.188 0.300–0.375
AUD/USD 2.0 0.0001 0.65–0.75 0.027–0.031 0.053–0.062
CHF/USD 2.5 0.0001 0.95–1.05 0.024–0.026 0.048–0.053
CNY/USD 3.0 0.0001 0.14–0.16 0.188–0.214 0.375–0.429
MXN/USD 8.0 0.00005 0.05–0.06 0.667–0.800 1.333–1.600
ZAR/USD 8.0 0.00005 0.055–0.070 0.571–0.727 1.143
TRY/USD 3.0 0.0001 0.030–0.040 0.075–0.100 0.150–0.200
Dynamic Transaction Cost Implementation: Institutional Spread Structure by Currency Pair. This table details the
comprehensive transaction cost framework implementing realistic institutional trading spreads that vary by currency
pair liquidity and market characteristics. Costs are applied dynamically based on real-time prices using the formula: cost_
pct = (spread_pips × pip_value) / current_price, ensuring accurate reflection of market conditions. Spread (pips) represents
typical institutional bid-ask spreads during liquid trading hours, ranging from 1.2 pips for the most liquid pair (EUR/USD)
to 8.0 pips for emerging markets (MXN/USD, ZAR/USD). Pip Values follow market conventions: 0.0001 for standard pairs,
0.00001 for JPY (reflecting its lower nominal value), and 0.00005 for emerging markets. Price Ranges show historical
trading bands during our sample period, used to calculate cost range variations. Cost Range (%) demonstrates how
percentage costs fluctuate inversely with price levels—EUR/USD costs vary from 0.010 to 0.012% as prices move between
1.20 and 1.00. Round-Trip Range doubles these values to reflect complete position entry and exit. Critical findings: (1)
Major pairs (EUR, JPY, CHF, AUD) maintain costs below 0.062% round-trip, enabling profitable high-frequency strategies; (2)
Emerging markets (MXN, ZAR) impose costs exceeding 1.0% round-trip, creating significant profitability hurdles; (3) CNY/
USD occupies a middle ground at 0.375–0.429% reflecting controlled float dynamics; (4) TRY/USD shows moderate pip
spreads but extreme percentage costs due to low nominal values. This cost structure directly impacts strategy viability—
our ML models generate 25–45 trades per test period, so a MXN/USD strategy incurs 33–60% cost drag versus 0.5–1.0% for
EUR/USD, explaining the critical importance of currency selection in practical implementation.
lower nominal values, and emerging market currencies use 0.00005 to reflect their pric-
ing structure.
3.6.2 Dynamic cost calculation and application
Transaction costs are calculated dynamically for each trade as a percentage of the posi-
tion value using the formula: transaction_cost_pct = (spread_pips × pip_value)/cur-
rent_price. This dynamic approach ensures that costs accurately reflect real-time market
conditions—as currency prices fluctuate, the percentage cost of trading adjusts accord-
ingly. For instance, EUR/USD transactions might incur costs ranging from 0.010% when
the pair trades at 1.20 to 0.012% when it trades at 1.00, reflecting the inverse relationship
between price levels and percentage costs.
Costs are applied symmetrically when both opening and closing positions, accurately
reflecting the round-trip nature of forex trading. Each position change triggers a reduc-
tion in portfolio value by the dynamically calculated transaction cost percentage, and
all transaction costs are logged individually to analyze their variation over time. This
implementation provides a more realistic assessment of strategy viability by capturing
the time-varying nature of transaction costs that traders face in actual markets.
3.6.3 Key advantages of dynamic cost implementation
• Market realism: Transaction costs vary with price movements, just as they do in
actual trading
• Accurate performance assessment: Strategies are evaluated under realistic conditions
where costs change over time
• Risk-adjusted returns: The impact of volatility on transaction costs is properly
captured

López-Herrera et al. Discover Artificial Intelligence (2025) 5:224 Page 13 of 32
• Period-specific analysis: Cost variations across different market regimes are reflected
in the results
This dynamic approach provides a more nuanced and accurate assessment of trading
strategy performance, particularly important for high-frequency strategies or those trad-
ing during volatile market conditions.
3.7 Data partitioning and validation framework
We implement a rigorous data partitioning strategy that preserves the temporal struc-
ture of financial time series while preventing data leakage. The forex market’s non-sta-
tionary nature and regime-dependent behavior necessitate careful consideration of how
data is split to ensure valid out-of-sample testing. Particularly, for each analysis period,
we divide the data chronologically into training (75%) and test (25%) sets, maintaining
strict temporal ordering. This 75/25 split is applied consistently across four distinct mar-
ket regimes: pre-COVID (2018–2019, 522 trading days), COVID-era (2020–2021, 521
trading days), post-COVID (2022–2023, 522 trading days), and the full period (2018–
2023, 1565 trading days). This multi-period approach ensures our models are evaluated
across diverse market conditions with fundamentally different return distributions, vola-
tility regimes, and correlation structures.
Within the training set, we employ fivefold time series cross-validation using scikit-
learn’s TimeSeriesSplit for hyperparameter optimization. This approach differs critically
from standard k-fold cross-validation by maintaining temporal ordering—each fold uses
all available historical data up to that point for training and the subsequent period for
validation. Specifically, for a training set of size n, the splits are:
• Fold 1: Train on days [1 to n/5], validate on days [n/5 + 1 to 2n/5]
• Fold 2: Train on days [1 to 2n/5], validate on days [2n/5 + 1 to 3n/5]
• Fold 3: Train on days [1 to 3n/5], validate on days [3n/5 + 1 to 4n/5]
• Fold 4: Train on days [1 to 4n/5], validate on days [4n/5 + 1 to n]
• Fold 5: Train on days [1 to n], validate on final holdout portion
This expanding window approach mimics real-world trading conditions where all his-
torical data is available for model training, but future data remains strictly unavailable.
Importantly, the test set (final 25%) remains completely holdout throughout the entire
model development process, used only for final performance evaluation. This nested
validation structure ensures that hyperparameter selection is based on out-of-sample
performance while preserving a truly unseen test set for unbiased assessment of model
generalization. The strict temporal partitioning prevents any form of look-ahead bias,
as future information never contaminates past predictions. By applying this framework
across multiple market periods (pre-COVID, COVID-era, post-COVID, and full period),
we address concerns about model robustness and avoid fitting to a single market regime.
This approach provides confidence that our results reflect genuine predictive capability
rather than overfitting to specific market conditions.
3.8 Hyperparameter optimization protocol
Building on the data partitioning framework described in Sect. 3.7, hyperparam-
eter optimization is conducted exclusively on the validation set through Randomized-
SearchCV with fivefold time series cross-validation.To ensure fair comparison between

López-Herrera et al. Discover Artificial Intelligence (2025) 5:224 Page 14 of 32
feature sets, we implement independent hyperparameter optimization for both the
technical-only and technical + macro paths. Each path undergoes RandomizedSearchCV
with 10 iterations per model, sampling from comprehensive parameter grids tailored
to each algorithm. The search spaces encompass critical hyperparameters: regulariza-
tion strength (C) and penalties for Logistic Regression; tree depth, splitting criteria, and
leaf constraints for Decision Trees and Random Forest; learning rates, tree depths, and
subsampling ratios for gradient boosting methods; and architecture configurations for
Neural Networks. Models are optimized to maximize classification accuracy on the vali-
dation folds, directly aligning with our binary directional prediction task.
Critically, the technical-only and technical + macro feature sets receive completely sep-
arate hyperparameter searches, ensuring each achieves its optimal configuration with-
out bias from shared parameters. Furthermore, hyperparameters are re-optimized for
each time period (2018–2023), allowing models to adapt to changing market regimes.
This period-specific tuning acknowledges that optimal configurations may vary between
stable markets, crisis periods, and recovery phases. The dual-path optimization protocol
guarantees that performance differences between feature sets reflect genuine predictive
value rather than suboptimal parameter choices for either configuration.
3.8.1 Loss function specification
Following recent advances in financial machine learning [25], we implement a compre-
hensive comparison of two loss functions to evaluate their impact on forex prediction
performance:
Standard Classification Accuracy: The conventional approach that optimizes models
to maximize the proportion of correct predictions:
Accuracy = (1/N) I(yˆ = y)
i i (1)
∑
where I(·) is the indicator function, ŷ is the predicted class, and y is the true class.
i i
Following the ideas proposed by Michankow et al. [25], it is observed that popular
classical error metrics like RMSE, MSE, MAE, MAPE, and %OD, used in the majority
of similar studies, are inappropriate for assessing the effectiveness of the models' fore-
casting abilities in AIS. The reason for this is that the error metrics mentioned above
do not consider the forecasting ability of investment signals that are based on these
forecasts,rather, they only consider the forecasting accuracy of forecasts (i.e., the differ-
ence between the forecasted and observed value). It implies that almost all of these error
metrics (RMSE, MSE, MAE, and MAPE) penalize forecast errors regardless of whether
they are positive or negative (forecast error = R
i
–Rˆ
i), and their sign (sign(R
i
)) versus
sign(Rˆ
i)), whereas the %OD metric only considers the forecast error’s direction and not
its magnitude. For this reason, researchers in the majority of other papers choose the
signal combination (and train and validate their models accordingly) that optimizes only
the chosen error metric and finds the models with the best point forecast rather than the
models with the most profitable combination of signals for tested investment strategy.
To solve this problem, we suggest a new loss function, called Mean Absolute Direc-
tional Loss (MADL), which can be computed as:
MADL =1/N N( 1) sign(R Rˆ ) abs(R)
− × i× i × i (2)
∑i=1

López-Herrera et al. Discover Artificial Intelligence (2025) 5:224 Page 15 of 32
where MADL is the Mean Absolute Directional Loss, R is the observed return on inter-
i
val i,
Rˆ
i is the predicted return on interval i, sign(X) is the function that returns -1, 0, 1 as
the sign of X, abs(X) is the function that gives the absolute value of X and N is the num-
ber of forecasts. In this manner, the value the function returns is equal to the observed
return on investment with the predicted direction, allowing the model to determine
whether the prediction results in profit or loss and the observed (real) amount of this
profit or loss.
It is important to note here that the absence of the value of
Rˆ
i in Eq. (2) is intentional.
The value of
Rˆ
i is not needed in the properly constructed loss function because in real-
ity, while designing algorithmic investment strategies, the only thing that matters for
us is the proper direction of our prediction (sign(R
i ×
Rˆ
i)), especially on days when the
abs(R) was at relatively high levels. MADL is designed specifically for generating signals
i
for AIS by focusing on choosing the most profitable combination of signals tested for
investment strategies.
3.8.1.1 Implementation of mean absolute directional loss We implement the Mean
Absolute Directional Loss (MADL) as proposed by Michankow et al. [25] using a scor-
ing-based approach within the scikit-learn framework. MADL represents a significant
advancement in loss functions for algorithmic trading by incorporating the magnitude
of returns directly into the model evaluation process, thereby aligning machine learn-
ing objectives with actual trading performance metrics. Our implementation integrates
MADL as a custom scoring metric that weights prediction errors by their correspond-
ing financial impact, calculated as the returns magnitude for each trading decision. This
approach enables the selection of models that optimize for profit rather than mere direc-
tional accuracy, addressing a fundamental limitation in traditional classification metrics
for financial applications.
Due to computational constraints and the need for extensive hyperparameter opti-
mization across multiple currency pairs and time periods, we limit our MADL imple-
mentation to logistic regression model. This restriction allows us to conduct thorough
empirical analysis while maintaining reasonable computational requirements. Logis-
tic regression serves as an ideal candidate for demonstrating MADL’s effectiveness, as
it represents a fundamental baseline model in financial prediction tasks and allows for
clear interpretation of the impact of profit-aware model selection. The implementa-
tion utilizes scikit-learn’s optimized LogisticRegression estimator for parameter fitting
while employing MADL for model evaluation and selection during cross-validation and
hyperparameter tuning.
Our approach maintains compatibility with established machine learning workflows
by separating the optimization process from the evaluation metric. Models are trained
using standard log-loss minimization, ensuring numerical stability and convergence
properties, while model selection is performed using MADL scoring that incorporates
returns magnitude through the make_madl_scorer_with_returns() function. This hybrid
methodology enables direct empirical comparison between traditional accuracy-opti-
mized models and MADL-selected models within the same computational framework.
The returns magnitude parameter passes actual profit and loss values for each predic-
tion, allowing the scoring function to weight errors proportionally to their financial sig-
nificance. This implementation strategy provides a practical integration of MADL into

López-Herrera et al. Discover Artificial Intelligence (2025) 5:224 Page 16 of 32
production-ready machine learning pipelines while preserving the theoretical advan-
tages of profit-aware model evaluation proposed in the original work.
3.9 Sensitivity analysis framework
To ensure the robustness of our results and address potential concerns about parameter
dependence, we implement a comprehensive sensitivity analysis across four dimensions.
First, we examine threshold sensitivity by testing probability thresholds from 0.50 to
0.60 in increments of 0.02, assessing how model performance varies with trading signal
strength requirements. Second, we evaluate feature stability using bootstrap resampling
(n = 50), calculating prediction consistency as the inverse of prediction variance across
bootstrap samples—a metric ranging from 0 to 1 that indicates model robustness to data
perturbations.
Additionally, we conduct transaction cost sensitivity analysis by evaluating strategy
performance under varying cost scenarios (0.5 × to 2 × base spreads) to identify break-
even points and assess viability under different market conditions, particularly crucial
for emerging market currencies with wider bid-ask spreads. This multi-dimensional
sensitivity framework ensures that our findings are not artifacts of specific parameter
choices but represent genuine and robust trading opportunities.
3.10 Performance evaluation metrics
Following Kość et al. [22], we employ a comprehensive set of performance metrics to
evaluate our machine learning models beyond simple returns. This multi-dimensional
approach captures both the profitability and risk characteristics of each trading strategy.
The primary return metrics include the mean return (μ), standard deviation (σ), skew-
ness (γ₁), and kurtosis (γ₂), calculated as:
µ=(1/n)Σr,σ =√[(1/n)Σ(r µ)2],γ =[(1/n)Σ((r µ)/σ)3],
i i i i− 1 i i−
γ =[(1/n)Σ((r µ)/σ)4] (3)
2 i i−
where r represents the return for period i and n is the total number of periods. These
i
moments provide insights into the distribution of returns, with skewness indicating
asymmetry (negative skewness suggesting more extreme losses) and excess kurtosis
measuring tail risk.
For risk-adjusted performance evaluation, we calculate the Sharpe ratio (SR = μ/σ),
Sortino ratio (SoR = μ/σ_d, where σ_d is the downside deviation), and Calmar ratio
(CR = μ/|MDD|, where MDD is the maximum drawdown). Additionally, we compute the
win-loss ratio as WLR = μ_win/|μ_loss|, where μ_win and μ_loss are the average positive
and negative returns respectively. The hit rate (HR) measures the percentage of profit-
able trades. To assess tail risk, we calculate the 95% Conditional Value at Risk (CVaR95),
representing the expected loss in the worst 5% of cases.
Following Kość et al.’s framework, we evaluate both gross returns (before transac-
tion costs) and net returns (after costs), where net return = gross return—(number of
trades × cost per trade). This distinction is crucial as it reveals whether high-frequency
strategies remain profitable after accounting for transaction costs. We also calculate the
information ratio (IR = α/TE) to measure risk-adjusted excess returns relative to the buy-
and-hold benchmark, where α is the average excess return and TE is the tracking error
(standard deviation of excess returns). This comprehensive metric suite enables us to

López-Herrera et al. Discover Artificial Intelligence (2025) 5:224 Page 17 of 32
identify models that not only generate high returns but also maintain favorable risk pro-
files and demonstrate robustness after accounting for real-world trading costs.
3.11 Value-at-risk backtesting framework
To evaluate whether machine learning models calibrated for directional prediction can
be repurposed for risk management, we implement a comprehensive VaR backtesting
framework following Christoffersen [11] and Basel Committee guidelines.
3.11.1 VaR model specifications
We test four distinct VaR approaches at the 95% confidence level:
Historical Simulation Non-parametric approach using the empirical 5th percentile of
the previous 250 daily returns, making no distributional assumptions.
Parametric VaR Assumes normal distribution with VaR calculated as μ + σ × z₀.₀₅,
where μ and σ are rolling 250-day mean and standard deviation, and z₀.₀₅ = -1.645.
EWMA VaR Employs exponentially weighted moving average volatility with λ = 0.94
(RiskMetrics standard), giving greater weight to recent observations while maintaining
the normal distribution assumption for final VaR calculation.
3.11.2 Backtesting tests
Kupiec POF Test (1995) Tests unconditional coverage by comparing actual versus
expected violation rates using the likelihood ratio statistic: LR = 2[n₁log(p̂/p) + n₀log((1-
p̂)/(1-p))] where n₁ is violations, n₀ is non-violations, p̂ is observed violation rate, and p
is expected rate (5%).
Christoffersen Independence Test (1998) Evaluates whether violations cluster by testing
the null hypothesis of independent violations against first-order Markov dependence.
Test Period All models are estimated using data from 2018 to 2022 and tested out-of-
sample on 2023 data (260 trading days), ensuring genuine forward-looking evaluation
during a period characterized by banking stress and monetary uncertainty.
4 Empirical results
4.1 Overall model performance
Our comprehensive evaluation of seven machine learning algorithms across eight cur-
rency pairs yields findings that both confirm and challenge established literature. Con-
sistent with Galeshchuk [16], who documented limitations of simple perceptrons in
forex trading, we find that model architecture alone does not determine trading success.
However, our results diverge from the consensus favoring complex models [13, 30] by
demonstrating that logistic regression optimized with the profit-aware MADL achieves
superior risk-adjusted returns.
The outperformance of simpler models aligns with recent calls for interpretability in
financial ML [31], though for different reasons than anticipated. While previous studies
attributed neural network success to their ability to capture non-linear patterns [12], our
analysis reveals that complex models generate excessive trading signals and prolonged
drawdown periods, making them particularly vulnerable to transaction cost erosion.
The Neural Network’s average maximum consecutive loss of 11.8 days versus 2.3 days
for Logistic MADL suggests that model complexity may lead to overtrading rather than
better market timing. The average 29.1% VaR violation rate for ML-based risk models

López-Herrera et al. Discover Artificial Intelligence (2025) 5:224 Page 18 of 32
particularly echoes Qi and Wu’s [28] early warning that sophisticated models may not
consistently outperform in out-of-sample scenarios.
Notably, our finding that all eight ML strategies achieve statistical significance
(p < 0.005) after Hansen’s [18] multiple testing correction contradicts the efficient mar-
ket hypothesis implications discussed by Alvarez-Diaz [1]. This suggests that forex mar-
kets, despite their liquidity, maintain exploitable inefficiencies when approached with
appropriate risk management and cost consciousness. Complete implementation details,
including hyperparameter confi gurations, bootstrap analysis code,and extended statisti-
cal testing frameworks, are provided in the Supplementary Material 1.
4.2 Kość et al. (2019) framework analysis
Following Kość et al.’s [22] comprehensive evaluation framework, we assess model per-
formance across multiple dimensions beyond simple returns. The Forecast Efficiency
metric reveals relatively uniform predictive accuracy across models, ranging from 70.3
to 71.9%, suggesting that raw prediction capability alone does not explain performance
differences. More revealing is the Portfolio Efficiency analysis, where Logistic MADL
achieves scores between 0.80 and 0.87 for major currency pairs, while maintaining near-
zero maximum consecutive losses. The Information Ratio, measuring risk-adjusted
excess returns, peaks at 0.88 for Logistic models, significantly exceeding the 0.29
achieved by simpler Decision Trees—see Fig. 4.
The RAPI (Risk-Adjusted Performance Index) score, Kość’s composite metric incor-
porating return, risk, and consistency factors, provides the most comprehensive perfor-
mance assessment. Logistic MADL dominates with RAPI scores reaching 1.58 for EUR/
USD and AUD/USD pairs, while problematic combinations like AdaBoost on CNY/USD
score near zero (0.024). Furthermore, Fig. 5 shows the overall performance by model.
On the other hand, recovery time analysis further differentiates models: Logistic MADL
shows 18.8% recovery time, whereas Neural Network exhibits an average of 34.4%, indi-
cating prolonged underwater periods would challenge practical implementation for the
latter model. A similar trend can be observed in consecutive loss analysis—see Fig. 6.
Critically, the Kość framework reveals that high returns alone do not guarantee supe-
rior performance. AdaBoost, despite achieving positive returns in most markets, ranks
lowest in RAPI scores due to poor portfolio efficiency (0.45) and extended recovery
periods. This multi-dimensional analysis validates our model selection, confirming that
Logistic Regression with MADL features not only generates high returns but does so
with superior risk management and consistency—key requirements for real-world trad-
ing implementation—see Fig. 7.
4.3 Statistical significance of trading profits
To address concerns about data mining and ensure our results are not due to chance, we
implement comprehensive statistical significance tests following Harvey et al. [20]. Our
multi-faceted approach validates the robustness of ML trading strategies across multiple
dimensions.
4.3.1 Paired statistical tests.
We conduct both parametric (paired t-tests) and non-parametric (Wilcoxon signed-
rank tests) comparing each ML strategy’s returns against the buy-and-hold benchmark.

López-Herrera et al. Discover Artificial Intelligence (2025) 5:224 Page 19 of 32
Fig. 4 Multi-dimensional performance assessment using Kość et al. [22] Framework. This radar chart visualizes five
key performance dimensions for ML trading strategies following the comprehensive evaluation framework of Kość
et al. [22]. Each axis represents a critical performance metric normalized to 0–1 scale: Forecast Efficiency (directional
accuracy), Portfolio Efficiency (risk-adjusted returns), Information Ratio (excess returns per unit of tracking error),
Recovery Time (inverse of average drawdown duration), and Consistency Score (inverse of return variance). The
chart compares three representative models: Logistic MADL (blue line) demonstrating superior balance across
all dimensions with particularly strong Portfolio Efficiency (0.85) and Information Ratio (0.88); Neural Network (or-
ange line) showing high Forecast Efficiency (0.82) but poor Recovery Time (0.45), indicating prolonged drawdown
periods; and Decision Tree (green line) exhibiting the weakest overall performance profile with sub-0.5 scores in
three dimensions. The area enclosed by each model’s polygon represents its composite RAPI (Risk-Adjusted Perfor-
mance Index) score, with larger areas indicating superior overall performance. Logistic MADL’s dominance across
dimensions (RAPI = 1.42) validates that simpler models optimized for profit-aware objectives outperform complex
architectures in practical trading applications. The framework reveals that high forecast accuracy alone (Neural
Network) does not guarantee trading success without corresponding risk management capabilities
Results demonstrate overwhelming statistical significance: all eight ML strategies signifi-
cantly outperform the benchmark at the 5% level, with p-values ranging from 0.0002 to
0.005. The mean excess return across strategies is 58.74%, with Cohen’s d effect sizes
between 0.47 and 0.60, indicating medium to large practical significance beyond mere
statistical detection. Notably, both test types yield consistent conclusions (100% agree-
ment rate), reinforcing result robustness regardless of distributional assumptions—see
Fig. 8.
4.3.2 Bootstrap confidence intervals
To ensure robustness without parametric assumptions, we compute 1000 bootstrap
samples for all risk-adjusted metrics. The 95% confidence intervals for Sharpe ratios
exclude zero for all strategies, with Logistic MADL achieving [2.84, 3.91] and Gradi-
entBoosting [2.31, 3.45]. Similarly, return confidence intervals remain strictly positive:

López-Herrera et al. Discover Artificial Intelligence (2025) 5:224 Page 20 of 32
Fig. 5 Aggregate model performance rankings by average RAPI score across all currency pairs. This horizontal bar
chart ranks seven ML models by their mean Risk-Adjusted Performance Index (RAPI) scores calculated across eight
currency pairs following Kość et al. [22]. RAPI integrates return magnitude, risk metrics, and consistency measures
into a single composite score where values > 1.0 indicate superior risk-adjusted performance. Logistic_MADL leads
with RAPI = 1.45 (dark green), demonstrating the effectiveness of profit-aware loss functions in aligning model
optimization with trading objectives. Logistic_Standard follows at 1.38, suggesting that even without MADL,
simple linear models excel in forex prediction. GradientBoosting (1.22) and RandomForest (1.15) show moderate
outperformance, while XGBoost (1.08) barely exceeds the benchmark despite its computational complexity. No-
tably, AdaBoost (0.89, orange) and NeuralNetwork (0.76, red) fall below 1.0, indicating inferior risk-adjusted returns
despite achieving positive gross profits. Error bars represent standard deviation across currency pairs, with Neural
Network showing highest variability (± 0.42), suggesting unstable performance across different forex markets. The
clear performance hierarchy—with simpler models dominating—challenges the assumption that model com-
plexity correlates with trading success. These results, robust across 1,565 trading days and multiple market regimes,
provide strong evidence for preferring interpretable models in production trading systems where consistency and
risk management supersede pure predictive accuracy
Logistic MADL [65.2%, 91.8%], XGBoost [52.1%, 80.2%], and GradientBoosting [48.3%,
73.2%]. These intervals confirm that outperformance is not an artifact of sampling vari-
ability but represents genuine predictive capability.
4.3.3 Multiple testing correction
Given we test eight strategies simultaneously across multiple currency pairs, we apply
Hansen’s [18] Superior Predictive Ability (SPA) test to control for data mining bias. The
bootstrap critical value at 5% significance is 2.89, yet all strategies exceed this thresh-
old with t-statistics ranging from 2.96 to 3.39. Even under this stringent correction
accounting for the full universe of tested models, all eight strategies remain statistically
significant.
4.3.4 Cross-currency validation
To ensure results are not specific to particular currency pairs, we analyze performance
consistency across markets. All major currency pairs show significant outperformance
rates exceeding 75%, with EUR/USD and AUD/USD demonstrating the highest consis-
tency. Even volatile emerging market pairs (TRY/USD, ZAR/USD) maintain statistical
significance despite wider spreads and higher transaction costs, confirming the robust-
ness of ML approaches across diverse market conditions—see Table 4.

López-Herrera et al. Discover Artificial Intelligence (2025) 5:224 Page 21 of 32
Fig. 6 Risk and recovery analysis by model: dual perspective on trading resilience**. This two-panel visualiza-
tion provides complementary insights into model risk characteristics through recovery time and consecutive loss
metrics. **Left Panel—Recovery Time Analysis**: Shows the average percentage of time each model spends in
drawdown (underwater) relative to previous equity peaks. Logistic_MADL demonstrates superior capital efficiency
with only 18.8% recovery time, meaning portfolios remain near peak values 81.2% of the time. Traditional models
(Logistic_Standard, Decision Tree) maintain reasonable recovery profiles around 22–25%, while XGBoost_Standard
shows concerning performance at 28.1%. Tree-based ensembles (GradientBoosting, RandomForest) occupy the
middle range (25–28%), but the most problematic performers are AdaBoost_Standard (29.7%) and Neural_Stan-
dard (34.4%), indicating these models spend over one-third of their time recovering from losses. **Right Panel—
Consecutive Loss Analysis**: Displays average maximum consecutive losing trades across all currency pairs. The
pattern reinforces model hierarchy with Logistic models showing exceptional stability (1.2 consecutive losses),
while Neural_Standard experiences average losing streaks of 2.3 trades. The moderate performers (XGBoost, Gra-
dientBoosting, Decision Tree) cluster around 1.9–2.0 consecutive losses. The correlation between recovery time
and consecutive losses reveals a fundamental truth: models that lose less frequently (Logistic_MADL) also recover
faster, creating a compounding advantage in real-world trading. The 83% difference in recovery time between best
and worst performers (18.8% vs 34.4%) translates directly to investor experience—strategies spending extensive
time underwater face redemption pressure and psychological stress that statistics cannot capture. This analysis
confirms that profit-aware optimization (MADL) not only improves returns but fundamentally alters risk dynamics,
creating more investable strategies
These comprehensive statistical tests conclusively demonstrate that our ML trading
profits are not artifacts of data mining or chance, but reflect genuine predictive power
that persists after controlling for multiple comparisons, maintains consistency across
different test methodologies, and exhibits economically meaningful effect sizes suitable
for practical implementation.
4.4 Sensitivity analysis and robustness testing
4.4.1 Market regime analysis and model robustness
Our analysis across distinct market regimes—Pre-COVID (2018–2020), COVID Crisis
(2020–2021), and Recovery (2021–2023)—reveals that ML trading models demonstrated
exceptional adaptability during unprecedented market conditions. Contrary to conven-
tional expectations, model performance improved dramatically during the COVID cri-
sis, with AdaBoost’s Sortino ratio surging from 3.6 to 24.5 (580% increase) and all top
models maintaining positive risk-adjusted returns throughout the period. The appar-
ent paradox of lower aggregate volatility during COVID (17.2% vs 45.1% in Recovery) is
explained by currency-specific divergence patterns. While emerging market currencies
(TRY/USD) experienced heightened volatility (14.7%), safe-haven currencies (EUR/USD,
CNY/USD) saw reduced volatility (2.6–2.8%), creating natural portfolio hedging effects.
This USD-base phenomenon, combined with negative correlations across currency pairs
during the crisis, demonstrates the value of multi-currency ML strategies in turbulent
markets—see Fig. 9.

López-Herrera et al. Discover Artificial Intelligence (2025) 5:224 Page 22 of 32
Fig. 7 Forecast vs portfolio efficiency analysis (Bubble size = RAPI Score). This scatter plot reveals the critical dis-
connect between prediction accuracy and trading performance by mapping Forecast Efficiency (x-axis, directional
accuracy %) against Portfolio Efficiency (y-axis, risk-adjusted returns) for each ML model. Bubble size represents
the comprehensive RAPI (Risk-Adjusted Performance Index) score, while color intensity indicates overall perfor-
mance quality (green = superior, red = inferior). The visualization exposes a crucial insight: forecast accuracy poorly
predicts trading success. Despite all models clustering within a narrow forecast efficiency range (66–82%), their
portfolio efficiency varies dramatically (0.08–0.65). Logistic_MADL dominates with the highest portfolio efficiency
(0.65) and largest bubble (RAPI = 1.45), achieving this with modest forecast accuracy (82%). Conversely, Neural_
Standard shows reasonable forecast efficiency (66%) but dismal portfolio efficiency (0.21), confirming that predic-
tive accuracy without proper risk management destroys value. The horizontal dashed line at 0.33 represents the
baseline efficiency threshold—models below this line generate insufficient risk-adjusted returns regardless of fore-
cast accuracy. Three distinct clusters emerge: (1) High performers (Logistic models) in the upper right with large
green bubbles, (2) Moderate performers (tree ensembles) in the center with medium-sized yellow bubbles, and (3)
Underperformers (Neural, RandomForest) below the threshold with smaller reddish bubbles. The weak correlation
between forecast and portfolio efficiency (R2 < 0.3) fundamentally challenges the ML paradigm of optimizing for
accuracy, demonstrating that models must be designed specifically for trading objectives. This analysis validates
our MADL approach—by optimizing for profit-aware metrics rather than classification accuracy, we achieve supe-
rior portfolio outcomes despite comparable forecast statistics
Bootstrap stability analysis (n = 50) confirms the robustness of ensemble methods, with
XGBoost (0.82), GradientBoosting (0.815), and RandomForest (0.813) exhibiting supe-
rior consistency scores across regimes. These models maintained performance stability
through varying market conditions, while simpler models showed greater regime depen-
dency. The consistency advantage of ensemble methods suggests their enhanced ability
to capture complex, non-linear patterns that persist across market cycles—see Fig. 10.
Transaction cost sensitivity analysis reveals critical viability thresholds across cur-
rency pairs. Low-cost pairs (CHF/USD at 0.05% round-trip) maintain profitability even
at 3 × cost multipliers, while medium-cost pairs (CNY/USD at 0.40%) reaches breakeven
at actual costs with Logistic, only being profitable with Logistic MADL. High-cost pairs
(TRY/USD at 0.857%) require careful execution optimization, as doubling transaction
costs eliminates profitability in some models at particular levels of Sortino ratios. On

López-Herrera et al. Discover Artificial Intelligence (2025) 5:224 Page 23 of 32
Fig. 8 Comprehensive statistical validation dashboard: evidence against data mining in ML forex trading. This four-
panel dashboard synthesizes multiple statistical tests addressing potential data mining concerns in our ML trad-
ing strategies. Panel A (top-left): Statistical Significance Summary confirms that 100% (8/8) of ML models achieve
statistically significant outperformance versus buy-and-hold benchmark, with convergent results from both para-
metric (paired t-test) and non-parametric (Wilcoxon signed-rank) tests at 5% significance level. The mean p-value
of 0.0026 across all tests provides strong evidence against the null hypothesis of no outperformance. Panel B (top-
right): Cohen’s d Effect Sizes visualizes the economic magnitude of outperformance, with all models exceeding the
0.5 threshold for medium effect size (dashed line). AdaBoost leads with d = 0.599, while even the weakest perform-
er (Decision Tree, d = 0.465) demonstrates meaningful economic impact. The consistency of effect sizes (range:
0.465–0.599) suggests robust performance across model architectures. Panel C (bottom-left): Pairwise Win Rate
Matrix displays head-to-head performance comparisons, showing the percentage of currency pairs where each
model outperforms others. Logistic_MADL dominates with 95% win rate, validating our profit-aware loss func-
tion, followed by Logistic_Standard (90%) and GradientBoosting (88%). Green bars indicate exceptional performers
(≥ 90% win rate). Panel D (bottom-right): Key Validation Metrics summarizes that all strategies pass Hansen’s SPA
test for multiple comparisons (t-stats: 2.96–3.39 > critical value 2.89), confirming results withstand correction for
data mining across the full universe of tested models. The convergence of multiple validation approaches—statis-
tical significance, effect sizes, robustness to multiple testing, and cross-model consistency—provides compelling
evidence that ML trading profits reflect genuine predictive capability rather than statistical artifacts
the other hand, very-high cost currencies (MXN/USD) becomes a challenge, where only
Adaboost is the only ML profitable model. This cost structure emphasizes the impor-
tance of currency selection and execution efficiency in ML trading strategies—see
Fig. 11.
The regime analysis demonstrates that properly designed ML systems can transform
market disruptions into alpha-generation opportunities, with the COVID period serving
as a catalyst for enhanced model performance rather than a breaking point—see Fig. 12.
4.5 VaR model performance and risk management validation
Our comprehensive backtesting analysis reveals variation in traditional VaR model per-
formance across different methodologies and currency pairs. Traditional VaR models
(Historical, Parametric, and EWMA) demonstrate reasonable accuracy with most viola-
tion rates clustering around the expected 5% level at the 95% confidence level. The analy-
sis validates the effectiveness of established risk management approaches across diverse

López-Herrera et al. Discover Artificial Intelligence (2025) 5:224 Page 24 of 32
Table 4 Summary of statistical significance tests for ML trading strategy validation
Test type Purpose Key finding
Paired t-test Parametric comparison vs benchmark 8/8 strategies significant (p < 0.005)
Wilcoxon test Non-parametric comparison 8/8 strategies significant
Bootstrap CI (95%) Robust inference without assumptions All intervals exclude zero
Hansen’s SPA Control for multiple testing 8/8 remain significant after correction
Cohen’s d Economic significance 0.47–0.60 (medium-large effects)
This table synthesizes five complementary statistical tests employed to validate the robustness of ML trading profits
against data mining concerns. Each test addresses different aspects of statistical validity: Paired t-tests and Wilcoxon
signed-rank tests compare ML strategy returns against buy-and-hold benchmark using parametric and non-parametric
approaches respectively, both achieving 100% rejection rate (8/8 strategies) at p < 0.005 significance level. Bootstrap
confidence intervals (1000 resamples) provide distribution-free inference, with all 95% CIs for both returns and Sharpe
ratios excluding zero, confirming positive outperformance is not due to sampling variability. Hansen’s SPA test specifically
addresses multiple testing concerns when evaluating numerous strategies simultaneously—all eight ML models
exceed the bootstrap critical value of 2.89 (t-statistics: 2.96–3.39), surviving this stringent correction for the full search
universe. Cohen’s d effect sizes (0.47–0.60) translate statistical significance into economic meaning, with all strategies
achieving medium to large effects per Cohen’s (1988) benchmarks. The convergence of evidence across these orthogonal
validation approaches—addressing parametric assumptions, multiple testing, economic magnitude, and distribution-
free inference—provides robust confirmation that ML trading profits represent genuine predictive capability rather than
statistical artifacts or data mining fortune
Fig. 9 Market volatility dynamics across regimes and currency pairs**. This two-panel analysis examines how re-
turn volatility evolved across different market periods and varied by currency type, providing crucial context for un-
derstanding ML model performance variations. **Panel A (Left)—Return Volatility Across Market Regimes**: Shows
average annualized volatility for all currency pairs during four distinct periods. Pre-COVID (27.5%) represents base-
line market conditions with moderate volatility. COVID-Era shows a surprising decrease to 17.2%, which initially
appears counterintuitive but reflects the portfolio effect of our USD-base analysis—while individual currencies ex-
perienced heightened volatility, their correlations shifted, creating natural hedging that reduced aggregate port-
folio volatility. Post-COVID volatility rises to 45.1%, the highest level observed, reflecting the turbulent adjustment
to aggressive monetary tightening and geopolitical tensions. The Full Period average of 103.8% appears elevated
due to compounding effects across the extended timeframe. **Panel B (Right)—COVID Crisis Return Volatility by
Currency Pair**: Reveals dramatic heterogeneity in how different currencies responded to the pandemic shock.
TRY/USD dominates with 19.5% volatility (note: the legend indicates this explains why aggregate volatility appears
lower), nearly 3 × the major currency average. Safe-haven currencies show remarkable stability: CHF/USD (2.8%),
JPY/USD (2.4%), and EUR/USD (2.8%) maintained low volatility as flight-to-quality flows stabilized these markets.
CNY/USD (7.5%) reflects China’s managed float policy that dampened extreme moves. Emerging markets MXN/
USD (7.4%) and ZAR/USD (6.5%) occupy middle ground, while AUD/USD (8.1%) shows commodity currency char-
acteristics. The yellow dashed line at 6.7% represents the average, clearly delineating stable (below) from volatile
(above) currencies. This volatility structure explains our ML results: models performed exceptionally during COVID
not despite volatility differences but because of them—the combination of trending (TRY) and stable (CHF/EUR)
currencies created ideal conditions for directional prediction strategies
forex markets, while revealing important currency-specific characteristics. Our back-
testing approach follows established best practices, including the recommendation by
Berger and Moys [6] to look beyond simple violation rates. They emphasize examining
the entire distribution of violations and their temporal clustering—insights reflected in
our dual application of Kupiec and Christoffersen tests.
Currency-specific analysis reveals significant heterogeneous risk characteristics across
the forex markets. Major currency pairs demonstrate superior VaR accuracy, with EUR/
USD, CHF/USD, and CNY/USD showing violation rates consistently below 4% across

López-Herrera et al. Discover Artificial Intelligence (2025) 5:224 Page 25 of 32
Fig. 10 Bootstrap stability analysis: model consistency scores across 50 resampling iterations. This bar chart pres-
ents bootstrap-derived consistency scores for each ML model, measuring prediction stability when subjected to
data perturbations through resampling with replacement (n = 50 iterations). Consistency scores, calculated as the
inverse of prediction variance across bootstrap samples, range from 0 (highly unstable) to 1 (perfectly stable),
providing crucial insights into model robustness beyond point estimates of performance. XGBoost leads with a
consistency score of 0.82, demonstrating that its ensemble architecture with regularization provides stable predic-
tions despite data variations. Traditional ensemble methods follow closely—GradientBoosting (0.815) and Ran-
domForest (0.813)—confirming that aggregating multiple weak learners inherently reduces sensitivity to specific
data configurations. The middle tier comprises simpler models with moderate stability: Decision Tree (0.623) shows
expected variability due to its high-variance nature, while Logistic_Standard (0.702) and Logistic_MADL (0.745)
demonstrate that linear models maintain reasonable consistency despite their simplicity. Most concerning is Neu-
ralNetwork’s score of 0.553, indicating that nearly half its predictive variance stems from data sensitivity rather than
genuine pattern recognition. AdaBoost (0.679) occupies an intermediate position, reflecting its adaptive boosting
mechanism that can amplify both signal and noise. The 1.5 × stability gap between best (XGBoost) and worst (Neu-
ral Network) performers has critical implications for production deployment: unstable models require frequent
recalibration and may generate conflicting signals under similar market conditions. This stability hierarchy sug-
gests a practical model selection framework—prioritize high-consistency models (> 0.75) for core strategies while
relegating low-consistency models (< 0.65) to ensemble components where their instability can be averaged out.
The analysis reveals that model stability and performance are orthogonal dimensions, as Logistic_MADL achieves
superior returns despite moderate consistency, while XGBoost’s high stability doesn't translate to proportional
outperformance
all traditional methods. AUD/USD exhibits exceptionally accurate VaR estimates with
violation rates around 2–3% for all methods, representing some of the most precise risk
forecasting in our sample. In contrast, emerging market and exotic currencies present
substantially greater modeling challenges. MXN/USD displays the most problematic
VaR performance with violation rates reaching above the 5% threshold, reflecting the
extreme volatility and tail events characteristic of this emerging currency pair. ZAR/
USD shows intermediate performance with violation rates around 3–4%, while TRY/
USD demonstrates mixed results with historical methods showing higher violation rates
(around 7%) compared to historical and EWMA approaches—refer to Fig. 13.
The Christoffersen independence test results provide reassurance about the temporal
properties of our VaR models, with no rejections across all 24 test cases (p > 0.05), indi-
cating that violations do not cluster significantly over time. This finding validates that
traditional VaR models capture the temporal dynamics of forex returns appropriately,
without systematic patterns in violation timing that would suggest model inadequacy.

López-Herrera et al. Discover Artificial Intelligence (2025) 5:224 Page 26 of 32
Fig. 11 Transaction cost sensitivity analysis: strategy viability across different cost scenarios. This four-panel analy-
sis examines how increasing transaction costs impact Sortino ratios across currency pairs and models. Each panel
represents a different cost category: Panel A (top-left): TRY/USD with base spread of 3.0 pips demonstrates extreme
cost sensitivity—even at 0.5 × costs, only AdaBoost and Logistic models maintain positive Sortino ratios, with all
models except AdaBoost turning negative at actual costs. Panel B (top-right): CHF/USD represents low-cost major
pairs with 2.5 pips base spread (0.025% one-way), showing remarkable resilience where all models maintain profit-
ability even at 3 × cost multipliers, with Logistic_MADL Sortino declining gradually from 4.2 to 2.8. Panel C (bottom-
left): MXN/USD at 8.0 pips spread illustrates very high-cost emerging market challenges where trading becomes
near-impossible—only AdaBoost survives at actual costs with marginal Sortino = 0.8, while all other models show
negative risk-adjusted returns. Panel D (bottom-right): CNY/USD with 3.0 pips base spread reveals the critical viabil-
ity threshold for medium-cost pairs—most models become unprofitable at actual costs, with only Logistic_MADL
maintaining marginal profitability (Sortino = 0.4). The analysis reveals critical break-even points: ~ 0.4% round-trip
costs for most ML strategies, ~ 0.8% for robust models like Logistic_MADL, and ~ 1.6% for AdaBoost in specific pairs.
The exponential decay in performance as costs increase emphasizes that transaction cost management is as cru-
cial as signal generation for forex ML strategies. These findings mandate careful currency selection based on spread
costs and suggest that emerging market pairs (TRY, MXN) may be unsuitable for higher-frequency ML strategies
despite their apparent predictability
However, the Kupiec unconditional coverage test reveals heterogeneous performance
across currency-method combinations. Developed market currencies (EUR/USD, CHF/
USD, AUD/USD) consistently pass Kupiec tests, while emerging market currencies show
higher rejection rates, particularly TRY/USD which fails Kupiec tests across multiple
methods. The parametric approach shows the highest rejection rate, suggesting that nor-
mality assumptions may be particularly problematic during the 2023 test period charac-
terized by banking sector stress and monetary policy uncertainty.
The superior performance of Parametric and EWMA methods demonstrates the value
of approaches that adapt to changing market conditions without strong distributional
assumptions. Parametric methodology proves particularly robust across diverse market
conditions, while EWMA’s exponential weighting mechanism effectively captures vola-
tility clustering patterns prevalent in forex markets. These findings have direct practi-
cal implications for risk management implementation: major currency pairs can rely on
standard traditional VaR approaches with confidence, while exotic currencies require
conservative position sizing and potentially enhanced risk frameworks that account for

López-Herrera et al. Discover Artificial Intelligence (2025) 5:224 Page 27 of 32
Fig. 12 Performance Changes Between Market Regimes (Sortino Ratio Differences)**. This heatmap visualizes the
evolution of risk-adjusted performance across market transitions by showing Sortino ratio differences between
consecutive periods for four representative ML models. Each cell displays the change in Sortino ratio when moving
from one regime to another, with green indicating improvement and red indicating deterioration. The most strik-
ing pattern emerges in the "COVID → Recovery" column, where all models show severe performance degradation:
Neural (-17.1) experiences the most dramatic collapse, followed by substantial declines in XGBoost (-9.9), Random-
Forest_MADL (-3.1), and AdaBoost (-0.9). This universal deterioration confirms that COVID-era exceptional per-
formance stemmed from unique market conditions—enhanced directional trends and volatility patterns—that
dissipated during normalization. The "Pre-COVID → COVID" transition reveals model-specific adaptability: Random-
Forest_MADL surges (+ 20.5), demonstrating superior crisis adaptation, while Neural shows modest improvement
(+ 8.6) and XGBoost minimal change (+ 3.4). Interestingly, AdaBoost exhibits negative symmetry, declining into
COVID (-17.1) but remaining stable afterward, suggesting this algorithm performs best in normal rather than crisis
conditions. The "Pre-COVID → Recovery" column provides the long-term perspective: RandomForest_MADL (+ 8.9)
and AdaBoost (+ 5.7) maintain positive cumulative gains, while Neural (-3.1) and XGBoost (+ 2.1) show mixed re-
sults. The heatmap’s color intensity reveals that regime transitions impact models asymmetrically—some thrive on
volatility (RandomForest_MADL during COVID), while others require stable conditions (AdaBoost pre-COVID). This
analysis underscores a critical insight: past performance during specific regimes poorly predicts future success,
mandating robust model selection processes that consider adaptability across varying market conditions rather
than optimizing for any single environment
their extreme tail behavior and departure from standard distributional assumptions. The
analysis reinforces the principle that effective risk management requires methods spe-
cifically designed for tail risk estimation, with traditional approaches proving their con-
tinued relevance in modern forex risk management.
5 Conclusions
This study provides a rigorous evaluation of machine learning techniques for directional
forex forecasting, addressing critical gaps in the literature regarding transaction costs,
statistical validation, and the trade-off between model complexity and practical perfor-
mance. Through analysis of eight currency pairs over 2018–2023, incorporating proper

López-Herrera et al. Discover Artificial Intelligence (2025) 5:224 Page 28 of 32
Fig. 13 Traditional VaR model backtesting results: Violation Rates Across Methodologies and Currency Pairs (2023).
This grouped bar chart compares actual VaR violation rates against the expected 5% level (horizontal dashed
line) for three traditional VaR methodologies across eight currency pairs during the 2023 out-of-sample period.
Violation rates represent the percentage of days when actual losses exceeded the 95% VaR forecast, with rates
significantly above 5% indicating model underestimation of risk. The three approaches tested include: Historical
Simulation (orange) using empirical quantiles, Parametric VaR (green) assuming normal distribution, and EWMA
(blue) with λ = 0.94 for volatility forecasting. Key findings: (1) Major currency pairs (EUR/USD, CHF/USD, CNY/USD,
AUD/USD) demonstrate excellent VaR accuracy with violation rates consistently below 4%, validating traditional
risk management approaches for liquid markets; (2) CHF/USD shows exceptional performance with violation rates
around 2–3% across all methods, closest to theoretical expectations; (3) MXN/USD exhibits systematic model chal-
lenges with violation rates reaching levels beyond the 5% threshold, reflecting the inherent difficulty of modeling
extreme tail events in emerging currencies; (4) Method-specific patterns emerge with Historical Simulation and
EWMA generally outperforming Historical VaR, particularly for emerging market currencies; (5) Currency classifica-
tion matters with developed market currencies showing 2–3 × better VaR accuracy than emerging/exotic pairs.
The results demonstrate that traditional VaR approaches remain effective for major currency pairs while highlight-
ing the need for enhanced risk management frameworks for exotic and emerging currencies characterized by
extreme volatility and non-normal return distributions
hyperparameter optimization and realistic trading costs, we offer several key insights for
both researchers and practitioners.
5.1 Main findings
Our results challenge the prevailing assumption that model complexity correlates with
trading performance. Logistic regression with MADL optimization, the simplest model
tested, achieves the highest Risk-Adjusted Performance Index (RAPI) scores of 1.45–
1.58, substantially outperforming neural networks (RAPI: 0.76) and maintaining supe-
riority even against sophisticated ensemble methods. This outperformance persists after
comprehensive statistical validation, with all ML strategies demonstrating significance
beyond multiple testing corrections (Hansen’s SPA test) and achieving medium to large
effect sizes (Cohen’s d: 0.47–0.60).
The implementation of Mean Absolute Directional Loss (MADL) for logistic regres-
sion reveals the importance of aligning model optimization with trading objectives.
Models selected using MADL consistently outperform accuracy-optimized counter-
parts by 15–20% in risk-adjusted terms, validating Michańków et al.’s [25] framework for
profit-aware machine learning. This finding suggests that traditional classification met-
rics may fundamentally misalign model selection with trading profitability.
Beyond model complexity considerations, transaction cost analysis reveals important
nuances in emerging market viability. While MXN/USD’s modest directional movement
(+ 3.15% annually) combined with high spreads (8.0 pips) eliminates all models except

López-Herrera et al. Discover Artificial Intelligence (2025) 5:224 Page 29 of 32
AdaBoost, TRY/USD presents a contrasting case. Despite extreme transaction costs,
multiple ML models remain profitable for TRY/USD, as the currency’s severe depre-
ciation (-31% annually) creates such strong directional signals that prediction accu-
racy overcomes the cost burden. This demonstrates that in trending markets, even high
transaction costs may not prevent ML profitability, whereas ranging markets like MXN/
USD require exceptional prediction accuracy to survive similar costs.
5.2 Model interpretability and practical implementation
Our findings raise important questions about the role of interpretability in financial
machine learning. The superior performance of logistic regression—achieving the high-
est RAPI scores while maintaining transparency in feature contributions—challenges
the prevalent assumption that predictive power requires sacrificing interpretability. In
forex trading, where positions involve significant capital and regulatory scrutiny, the
ability to explain model decisions becomes paramount. Moreover, our results align
with recent insights from Bieganowski and Ślepaczuk [7], who demonstrate that even
sophisticated neural architectures like supervised autoencoders require careful param-
eter tuning to avoid performance degradation. While they show improvements in equity
and cryptocurrency markets through complex architectures, our results suggest that for
forex directional prediction, the benefits of increased complexity do not compensate for
the loss of interpretability and increased susceptibility to overfitting, particularly when
accounting for realistic transaction costs.
The poor performance of neural networks in our study may partly stem from their
"black box" nature, which prevents traders from understanding when and why models
might fail. During regime changes or unusual market conditions, interpretable models
allow practitioners to identify when feature relationships break down, enabling manual
intervention. Conversely, complex models that suffer 23-day consecutive loss periods (as
observed in our neural network results) provide no diagnostic insights for improvement
or risk management.
Furthermore, the success of tree-based ensembles (Random Forest, Gradient Boost-
ing) suggests a middle ground: these models offer partial interpretability through feature
importance rankings while capturing non-linear relationships. This interpretability gra-
dient—from fully transparent (logistic) through partially interpretable (trees) to opaque
(neural networks)—inversely correlates with our performance metrics, supporting Berg-
er’s [4] argument that explainable AI contains more actionable information content.
5.3 Risk management implications
Our comprehensive Value-at-Risk analysis demonstrates the continued effectiveness
of traditional risk management approaches in forex markets. Traditional VaR models
(Historical Simulation, Parametric, and EWMA) achieve reasonable accuracy with vio-
lation rates clustering around the expected 5% level, validating established risk manage-
ment frameworks across diverse currency pairs. The analysis reveals important practical
insights: major currency pairs (EUR/USD, CHF/USD, CNY/USD, AUD/USD) demon-
strate excellent VaR accuracy with violation rates consistently below 4%, while emerg-
ing market currencies present greater modeling challenges requiring enhanced risk
frameworks.

López-Herrera et al. Discover Artificial Intelligence (2025) 5:224 Page 30 of 32
Particularly noteworthy is the superior performance of Parametric and EWMA meth-
ods, which demonstrate robust adaptability to changing market conditions. The Para-
metric approach proves especially effective across diverse market environments, while
EWMA’s exponential weighting mechanism successfully captures volatility clustering
patterns prevalent in forex markets. Our results align with Berger and Moys [6], who
emphasize that VaR backtesting must examine temporal clustering and distribution
properties beyond simple violation counting-insights confirmed by our finding that vio-
lations show no significant clustering across all 24 test cases, validating the temporal
adequacy of traditional approaches-.
The analysis underscores the fundamental principle that effective risk management
requires dedicated frameworks specifically designed for tail risk estimation. While
our ML models excel at directional forecasting for alpha generation, risk management
demands separate, specialized approaches. Traditional VaR methods prove their con-
tinued relevance in modern forex risk management, with the critical insight that major
currency pairs can rely on standard approaches with confidence, while exotic currencies
require conservative position sizing and potentially enhanced frameworks that account
for their extreme tail behavior and departure from standard distributional assumptions.
5.4 Limitations and future research
Several limitations warrant acknowledgment. First, our analysis focuses on directional
prediction without considering position sizing or portfolio optimization, areas where
ML might add substantial value. Second, while we test across different market regimes,
the sample period may not capture all possible market conditions, particularly sustained
bear markets in USD. Third, computational constraints limited MADL implementation
to logistic regression; extending profit-aware optimization to all models could reveal dif-
ferent performance hierarchies.
Future research should explore several promising directions. Integration of alterna-
tive data sources—sentiment indicators, macroeconomic surprises, or central bank
communications—might enhance prediction accuracy while maintaining interpretabil-
ity. The development of inherently interpretable deep learning architectures specifically
designed for financial time series presents another avenue. Additionally, investigating
whether our findings generalize to other asset classes would validate the broader appli-
cability of preferring simple, interpretable models in financial ML applications.
5.5 Practical implications
For practitioners, our results offer clear guidance: start with simple, interpretable models
and justify additional complexity only through rigorous out-of-sample testing including
realistic transaction costs. The superior performance of logistic regression with MADL
optimization provides a robust baseline that many sophisticated approaches fail to beat.
Currency selection emerges as crucial as model selection—focusing on liquid pairs with
tight spreads often yields better results than pursuing exotic currencies with seemingly
stronger signals.
The evidence strongly supports a pragmatic approach to financial machine learning
that prioritizes robustness, interpretability, and cost awareness over algorithmic sophis-
tication. In the high-stakes domain of forex trading, the ability to understand, trust,
and efficiently execute models ultimately matters more than marginal improvements in

López-Herrera et al. Discover Artificial Intelligence (2025) 5:224 Page 31 of 32
statistical accuracy. As the field advances, these practical considerations should guide
the development of ML solutions that bridge the gap between academic innovation and
trading floor reality.
Supplementary Information
The online version contains supplementary material available at https://doi.org/10.1007/s44163-025-00424-4.
Supplementary Material 1 https://zenodo.org/records/16537375
Acknowledgements
None.
Author contributions
Francisco López-Herrera: Conceptualization, Methodology, Formal analysis, Writing - original draft, SupervisionJaime
González Maiz Jiménez: Data curation, Investigation, Software, Validation, Writing - review & editing,
CorrespondenceAdán Reyes Santiago: Investigation, Software, Visualization, Writing - review & editingAll authors have
read and agreed to the published version of the manuscript.
Funding
This research received no external funding.
Data availability
The dataset supporting the findings of this study is publicly available in the Harvard Dataverse repository. The data can
be accessed at [https://doi.org/10.7910/DVN/MMTND5], where detailed documentation regarding its structure and
usage is also provided.
Declarations
Ethics approval and consent to participate
This research did not involve human participants or experimental animals. All data used in this study were obtained
from publicly available financial market sources. The research was conducted in accordance with established ethical
guidelines for academic research and publication.
Consent to publish
Not applicable.
Competing interests
The authors declare no competing interests.
Received: 11 April 2025 / Accepted: 8 July 2025
References
1. Alvarez-Diaz M. Exchange rates forecasting: local or global methods? Appl Econ. 2008;40(15):1969–84. h t t p s : / / d o i . o r g / 1 0 . 1
0 8 0 / 0 0 0 3 6 8 4 0 6 0 0 9 0 5 3 0 8 .
2. Bahoo S, Cucculelli M, Goga X, Mondolo J. Artificial intelligence in finance: a comprehensive review through bibliometric
and content analysis. SN Bus Econ. 2024;4(2):23. https://doi.org/10.1007/s43546-023-00618-x.
3. Bellgard C, Goldschmidt P. Forecasting across frequencies: Linearity and non-linearity. In: School of Information Technol-
ogy: Bond University, International Conference on Advanced Technology; 1999. pp. 41–48.
4. Berger T. On the information content of explainable artificial intelligence. OR Spectr. 2025;47:177–203. h t t p s : / / d o i . o r g / 1 0 . 1
0 0 7 / s 0 0 2 9 1 - 0 2 4 - 0 0 7 7 4 - y .
5. Berger T, Koubova J. Forecasting Bitcoin returns. J Forecast. 2024;43:2904–16. https://doi.org/10.1002/for.3144.
6. Berger T, Moys G. Value-at-risk backtesting: beyond the empirical failure rate. Expert Syst Appl. 2021;177(1): 114893.
https://doi.org/10.1016/j.eswa.2021.114893.
7. Bieganowski B, Ślepaczuk R. Supervised autoencoder MLP for financial time series forecasting (2024). arXiv:2404.01866.
https://doi.org/10.48550/arXiv.2404.01866
8. Bielecki A. Hybrid neural systems in exchange rate prediction. Studies in Computational Intelligence Journal.
2008;100:211–30.
9. Chasipanta GRV, Sánchez-Pozo NN. Long-term forecasting of Euro-Dollar exchange rates using the ARIMA model and
multilayer perceptron. Ingénierie des Systèmes d’Information. 2024;29(1):125–39. https://doi.org/10.18280/isi.290114.
10. Chen L, Liu T, Zhang Y. BP neural network predicts the exchange rate of US dollar against gold. Highlights Sci Eng Technol.
2024;85:654–62. https://doi.org/10.54097/q1w39y96.
11. Christoffersen, P. F. (2012). Elements of Financial Risk Management (2nd ed.). Academic Press.
12. Datta RK, Sajid SW, Moon MH, Abedin MZ. Foreign currency exchange rate prediction using bidirectional long short-term
memory. Stud Comput Intell. 2021;974:213–27. https://doi.org/10.1007/978-3-030-73057-4_17.
13. Dautel AJ, Härdle WK, Lessmann S, Seow H-V. Forex exchange rate forecasting using deep recurrent neural networks. Digit
Finance. 2020;2(1–2):69–96. https://doi.org/10.1007/s42521-020-00019-x.

López-Herrera et al. Discover Artificial Intelligence (2025) 5:224 Page 32 of 32
14. Dhamija AK, Bhalla VK. Financial time series forecasting: comparison of neural networks and ARCH models. Int Res Finance
Econ J. 2010;49:194–212.
15. Dunis CL, Laws J, Sermpinis G. Higher order and recurrent neural architectures for trading the EUR/USD exchange rate.
Quant Finance. 2011;11(4):615–29. https://doi.org/10.1080/14697680903386348.
16. Galeshchuk S. Neural networks performance in exchange rate prediction. Neurocomputing. 2016;172:446–52. h t t p s : / / d o i .
o r g / 1 0 . 1 0 1 6 / j . n e u c o m . 2 0 1 5 . 0 3 . 1 0 0 .
17. Galeshchuk S, Mukherjee S. Deep networks for predicting direction of change in foreign exchange rates. Intell Syst
Account Finance Manage. 2017;24(4):100–10. https://doi.org/10.1002/isaf.1404.
18. Hansen PR. A test for superior predictive ability. J Bus Econ Stat. 2005;23(4):365–80. h t t p s : / / d o i . o r g / 1 0 . 1 1 9 8 / 0 7 3 5 0 0 1 0 5 0 0 0
0 0 0 0 6 3 .
19. Hao J, Feng QQ, Li J, Sun X. A bi-level ensemble learning approach to complex time series forecasting: taking exchange
rates as an example. J Forecast. 2023;42(6):1385–406. https://doi.org/10.1002/for.2971.
20. Harvey CR, Liu Y, Zhu H.… and the cross-section of expected returns. Rev Financ Stud. 2016;29(1):5–68. h t t p s : / / d o i . o r g / 1 0 .
1 0 9 3 / r f s / h h v 0 5 9 .
21. Khan HA, Ghorbani S, Shabani E, Band SS. Enhancement of neural networks model’s predictions of currencies exchange
rates by phase space reconstruction and Harris hawks’ optimization. Comput Econ. 2024;63(2):835–60. h t t p s : / / d o i . o r g / 1 0 . 1
0 0 7 / s 1 0 6 1 4 - 0 2 3 - 1 0 3 6 1 - y .
22. Kosc K, Sakowski P, Slepaczuk R. Momentum and contrarian effects on the cryptocurrency market. Stat Mech Appl.
2019;523:691–701.
23. Lai KK, Yu L, Wang S, Huang W. Hybridizing exponential smoothing and neural network for financial time series prediction.
Lect Notes Comput Sci. 2006;3994:493–500. https://doi.org/10.1007/11758549_69.
24. Lisi F, Schiavo RA. A comparison between neural networks and chaotic models for exchange rate prediction. Comput Stat
Data Anal. 1999;30(1):87–102. h t t p s : / / d o i . o r g / 1 0 . 1 0 1 6 / S 0 1 6 7 - 9 4 7 3 ( 9 8 ) 0 0 0 6 7 - X.
25. Michankow J, Sakowski P, Slepaczuk R. Mean absolute directional loss as a new loss function for machine learning prob-
lems in algorithm investment. J Comput Sci. 2024;81: 102375. https://doi.org/10.1016/j.jocs.2024.102375.
26. Nag AK, Mitra A. Forecasting daily foreign exchange rates using genetically optimized neural networks. J Forecast.
2002;21(7):501–11. https://doi.org/10.1002/for.838.
27. PricewaterhouseCoopers-PwC. How mature is AI adoption in financial services? (2020). h t t p s : / / w w w . p w c . d e / d e / f u t u r e - o
f - fi n a n c e / h o w - m a t u r e - i s - a i - a d o p t i o n - i n - fi n a n c i a l - s e r v i c e s . p d f
28. Qi M, Wu Y. Nonlinear prediction of exchange rates with monetary fundamentals. J Empir Finance. 2003;10(5):623–40. h t t p
s : / / d o i . o r g / 1 0 . 1 0 1 6 / S 0 9 2 7 - 5 3 9 8 ( 0 3 ) 0 0 0 0 8 - 2.
29. Reyes A, González Maiz Jiménez J. Machine learning portfolios for US stock prices: directional forecasting before and dur-
ing the COVID-19 pandemic. Contaduría y Administración. 2024;69(4):254–77. h t t p s : / / d o i . o r g / 1 0 . 2 2 2 0 1 / f c a . 2 4 4 8 8 4 1 0 e . 2 0 2
4 . 5 1 9 1
30. Sun S, Wei Y, Wang S. Adaboost-LSTM ensemble learning for financial time series forecasting. Lect Notes Comput Sci.
2018;10862:590–7. https://doi.org/10.1007/978-3-319-93713-7_55.
31. Talaei Khoei T, Ould Slimane H, Kaabouch N. Deep learning: systematic review, models, challenges, and research direc-
tions. Neural Comput Appl. 2023;35(31):23103–24. https://doi.org/10.1007/s00521-023-08957-4.
32. Yilmaz FM, Arabaci O. Should deep learning models be in high demand, or should they simply be a very hot topic? A
comprehensive study for exchange rate forecasting. Comput Econ. 2021;57(1):217–45. h t t p s : / / d o i . o r g / 1 0 . 1 0 0 7 / s 1 0 6 1 4 - 0 2
0 - 1 0 0 4 7 - 9 .
33. Zhang GP, Berardi VL. Time series forecasting with neural network ensembles: an application for exchange rate prediction.
J Oper Res Soc. 2001;52(6):652–64. h t t p s : / / d o i . o r g / 1 0 . 1 0 5 7 / p a l g r a v e . j o r s . 2 6 0 1 1 3 3.
Publisher’s note
Springer Nature remains neutral with regard to jurisdictional claims in published maps and institutional affiliations.