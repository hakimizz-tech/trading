Scalper Major: A Computational Solution for Automated
Trading in High Volatility Environments
Jose´ JeovaneR.Cordeiro1,2,ArlinoHenriqueM.deArau´jo2,GuilhermeA.Avelino2
1FederalInstituteofMaranha˜o(IFMA)
CoelhoNetoCampus–OlhoD’AguinhaNeighborhood
CEP:65.620-000–CoelhoNeto–MA
2FederalUniversityofPiau´ı(UFPI)
MinisterPetroˆnioPortellaUniversityCampus–IningaNeighborhood
CEP:64.049-550–Teresina–PI
jose.cordeiro@ifma.edu.br, {arlino, gaa}@ufpi.edu.br
Abstract. ResearchContext: Theforeignexchange(Forex)marketisthelargest
and most liquid in the world, characterized by high volatility and continuous
operation. In this environment, human decision-making is often compromised
by emotional biases and the limited ability to process large amounts of infor-
mation in real time. Scientific and/or Practical Problem: Traditional trading
strategies have weaknesses, including delayed signals and a lack of robust risk
metrics. Furthermore, many existing studies in the literature focus only on cu-
mulative return, neglecting the risk-return trade-off and practical applicability.
Proposed Solution and/or Analysis: This work presents Scalper Major, an au-
tomatedtradingsystemdesignedtooperateconsistentlyintheForexmarket. Its
modular architecture integrates technical and managerial heuristics, as well as
strict risk and capital management mechanisms. Related IS Theory: The re-
search is based on the principles of information systems, applied to automated
decision-making, aligning technical indicators, computational heuristics, and
financialmetricsasreliablesupporttoolsforinvestors. ResearchMethod: The
system was implemented in MQL5 on the MetaTrader 5 platform. The evalua-
tion was conducted through eight-year backtests on four major currency pairs,
taking into account commissions, execution delays, and various market scenar-
ios. Summary of Results: With an initial capital of $20,000.00, Scalper Major
achieved significant results: a net profit of $751,533.23, a win rate of 82.54%,
and a maximum drawdown of 9.43%. The Sharpe Ratio of 1.63 demonstrates
superior risk-return efficiency compared to related studies. Contributions and
Impact to IS area: The study, in addition to proposing an operational tool,
presents a methodological advancement by creating a novel compilation of the
mainevaluationindicatorsforautomatedtradingsystems.
1. Introduction
Trade among people has existed since ancient civilizations. However, the pillars of the
modern foreign exchange market began to consolidate in the 19th century with the emer-
gence of the gold standard system, which the Bretton Woods Agreement later reinforced
in 1944 [Bordo1993]. The idea underlying the gold standard dates back to David Hume
in 1752, who argued that international trade should be balanced through the flows of

precious metals [Caffentzis2001]. The gold standard was in effect until 1914 and was
later replaced in 1944 by the Bretton Woods Agreement, which pegged exchange rates
to the U.S. dollar. As part of this agreement, institutions such as the International Mon-
etary Fund (IMF) and the World Bank were created to promote global economic sta-
bility [Bordo1993]. However, in 1971, the United States abandoned the convertibil-
ity of the dollar to gold, ending the Bretton Woods system and ushering in the era of
floating exchange rate regimes, which characterize the modern foreign exchange mar-
ket[Meltzer1991].
The foreign exchange market, also known as Forex (Foreign Exchange Market),
stands out as the largest and most liquid in the world. Besides this one, there are other
markets, such as the stock market (equities), cryptocurrencies, futures, and derivatives,
among others. These segments handle billions and even trillions of dollars daily. For ex-
ample,onAugust12,2025,datafromNASDAQ1showedthatthevolumeofsharestraded
ontheCompositeindexwasapproximatelyUS$372.4billion. Inthecryptocurrencymar-
ket, data from July 2025 show that the total monthly trading volume was approximately
US$ 1.77 trillion2, which represents an average of US$ 57.1 billion per day. In turn, data
publishedbytheCMEGroup3,oneoftheworld’slargestderivativesexchanges,recorded
anaveragedailyvolume(ADV)ofUS$1.1trillionforstockindexfutures.
Although the values presented above are high, they do not surpass the trading
volume of the Forex market. The latest report released by the Bank for International
Settlements(BIS)4,withdatacollectedinApril2022,showsthattheaveragedailytrading
volumeinForexwasUS$7.5trillion–afigurehigherthanthatofanyothermarket. This
significant volume is a direct consequence of the unique characteristics of the foreign
exchange market, such as high liquidity and decentralization, which involve the buying
and selling of currencies among governments, financial institutions, corporations, and
individualinvestors[ElMahjoubyetal. 2024,OlorunsheyeandMeenakshi2024].
The combination of these characteristics, along with its continuous operation –
24 hours a day, 7 days a week – offers significant profit opportunities, particularly for
short-termstrategiessuchasscalpinganddaytrading[ZafeiriouandKalles2021]. How-
ever,althoughaccessibleandwithpotentialforgains,thismarketisinfluencedbyvarious
exogenous factors, including geopolitical events, economic announcements, and natu-
ral disasters, which significantly increase volatility and contribute to a volatile environ-
ment [Chantonaetal. 2020]. Furthermore, due to its noisy, non-stationary, chaotic, and
deterministic nature, predicting exchange rates represents a significant challenge for re-
searchersandinvestors[ElMahjoubyetal. 2024,Ismailetal. 2022].
Ismail et al. highlight that in this scenario, human performance is often com-
promised by emotional biases, such as fear, greed, and impatience, which can lead to
significantlosses. Furthermore,thespeedrequiredtocapitalizeonopportunitiesinshort-
term strategies, such as scalping, exceeds the human capacity to process information
and execute orders in a timely manner [Ismailetal. 2022]. To overcome these difficul-
ties, many traders resort to technical indicators. However, Povitukhin and Karmanova
1https://www.nasdaqtrader.com/Trader.aspx?id=DailyMarketSummary
2https://www.theblock.co/post/365199/crypto-exchange-volume-july
3https://br.tradingview.com/cme/
4https://www.bis.org/statistics/rpfx25_announcement.htm

[PovitukhinandKarmanova2020]pointoutthatthesetoolsare,forthemostpart,lagging
– that is, they react to price movements that have already occurred instead of accurately
predicting them. This characteristic often results in the generation of false or delayed
signals,leadingthetradertomakeerrorsand,consequently,sufferfinanciallosses.
To address these challenges, automated trading systems emerge as a promising
solution for executing strategies consistently and efficiently, reducing the influence of
emotional biases, and optimizing operational performance. However, in a recent survey
conducted by these researchers, they found that the Forex market is an underexplored
area in the scientific literature on algorithmic trading, despite its significant economic
importance. Nevertheless, existing works present significant methodological limitations,
suchasthelackofriskmetricsandtheabsenceoftestinginaliveenvironment.
The solution to this problem lies in creating a tool that automates the decision-
makingprocessbasedonobjectivecriteriaandspecializedheuristics. Thistoolmustalso
consideressentialevaluationmetrics,suchasReturn,Risk,andRisk-AdjustedReturn,to
ensure a disciplined and systematic execution of trades, even under adverse market con-
ditions. To this end, the present work introduces Scalper Major, an Expert Advisor (EA)
developed based on objective technical criteria, strict risk management rules, specialized
heuristics, and a modular architecture, which enables automatic operation with minimal
human intervention in the Forex market. To achieve this goal, the following specific ob-
jectiveswereestablished:
• Designamodulararchitecturecomposedofspecializedcomponents.
• Integratetechnicalandmanagerialheuristicstoidentifytradingopportunities.
• Establishariskandmoneymanagementmodelthatpromotesjudiciouscontrolof
exposureandresourceallocationintrades.
• Implement and validate the system in a simulated environment through backtests
withrealhistoricaldata,usingappropriatemetrics.
The adopted strategy was validated through a backtesting process that covered
the period from January 2016 to December 2023. For this simulation, Scalper Ma-
jor was configured to operate specifically on the currency pairs EUR/USD, GBP/USD,
USD/CAD, and USD/CHF. In this stage, an initial capital of $20,000.00 was used, and
the system achieved a total net profit of $751,533.23. This resulted from a gross profit
of $1,060,523.23 and gross losses of $308,991.00, which included trades closed with a
negative balance and operational costs. In total, 11,571 trades were executed, of which
7,217(62.37%)wereLong(buy)tradesand4,354(37.63%)wereShort(sell)trades. The
overallwinratewas82.54%,withan83.66%rateforLongtradesandan81.42%ratefor
Shorttrades.
Themaincontributionsofthisworkareasfollows:
1. Unpublished compilation of the main trading metrics used to evaluate automated
tradingsystems.
2. Asetoftechnicalandmanagerialheuristicsaimedatidentifyingtradingopportu-
nitiesandexecutingordersefficiently,withstrictriskcontrolandmoneymanage-
ment.
3. A modular architecture composed of specialized components that enable the im-
plementationoftheproposedapproach.

4. Afunctionalimplementationoftheproposedarchitectureandapproach,validated
throughextensivesimulationswithhistoricaldata.
The structure of this work is organized into sections that detail the investigated
problem and the proposed solution. Section 2 presents the theoretical background neces-
sary for understanding the study. Section 3 discusses the main related works. Section 4
describes the proposed solution in detail. Section 5 presents the empirical results ob-
tainedfromtheapplicationoftheproposedsolutioninasimulatedenvironmentwithreal
historicaldata. Finally,Section6presentstheconclusionsofthestudy.
2. Background
Thissectioncoverstheconceptualandtechnologicalfoundationsnecessarytounderstand
thiswork.
2.1. TheFinancialMarketandtheForexMarket
AccordingtoOlorunsheyeandMeenakshi[OlorunsheyeandMeenakshi2024],thefinan-
cial market has a significant influence on multiple aspects of society, including the econ-
omy, education, business, employment, and public safety. The foreign exchange mar-
ket, often abbreviated as Forex, is the global marketplace for trading currencies. Unlike
centralized stock exchanges, such as the NYSE or B3, the Forex market operates in a
decentralized manner on the Over-the-Counter (OTC) model; that is, transactions occur
directly between the involved parties, without the intermediation of a central exchange
[ElMahjoubyetal. 2024]. Forex transactions always occur in pairs; that is, the purchase
ofonecurrencysimultaneouslyimpliesthesaleofanother.
The exchange rate is determined by the interaction of supply and demand among
the parties involved, as well as by the economic conditions of the countries issuing the
currencies. Alargepartofthismarket’svolatilityisconcentratedinsevencurrencypairs.
Thesepairs–AUD/USD,EUR/USD,GBP/USD,NZD/USD,USD/CAD,USD/CHF,and
USD/JPY–arethemosttradedandaccountformorethanhalfoftheactivityintheForex
market [Weithers2011]. Weithers [Weithers2011] highlight that the daily transaction
volume in these pairs surpasses that of other financial markets, such as the stock market,
which reinforces their central importance to the liquidity and functionality of the Forex
market.
2.2. CandlestickPatterns
Candlestick patterns are a fundamental tool in financial technical analysis, originating
in Japan in the 18th century, where they were initially used to analyze rice prices. Al-
thoughthereisnoconsensusontheeffectivenessofthesepatterns,theiruseiswidespread
among professionals and investors [Heinzetal. 2021]. The literature presents a large
number of candlestick patterns, with references varying between 103 and 105 different
types[Vargheseetal. 2023]. Thesepatternscanbecategorizedinvariousways,withone
ofthemostcommonbeingbasedonthenumberofcandlesthatcomposethem.
OnenoteworthypatternistheMarubozu,whichisidentifiedasabullishMarubozu
when its low price is equal to or close to its opening price, and its high is equal to or
close to its closing price. The opposite constitutes a bearish Marubozu. This pattern also
has the following characteristics: (a) it indicates strong buying or selling pressure; (b) it

representsapotentialtrendcontinuationsignal;and(c)itisaclearandeasilyidentifiable
visualpattern.
2.3. TechnicalIndicators
Technical indicators are mathematical and statistical tools derived from historical price
and volume data of financial assets, used in technical analysis to predict future price
movements [Naranjoetal. 2018]. Naranjo et al. also highlight that technical indicators
provide a visual representation of market dynamics, helping investors and analysts iden-
tifytrends,turningpoints,andpricepatterns,andmakedecisionsabouttheoptimaltiming
foropeningorclosingpositions.
Almeida and Vieira [AlmeidaandVieira2023] point out that, among the most
widely used technical indicators in technical analysis, Moving Averages (MA) and the
RelativeStrengthIndex(RSI)standout,amongothers. Theauthorsalsohighlighttwoof
the most common and widely used types of moving averages: the Simple Moving Aver-
age (SMA) and the Exponential Moving Average (EMA). The SMA is calculated as the
arithmeticaverage of prices (P)over aspecific numberof periods(n). Itis usedto iden-
tify the general direction of a trend over time by smoothing out short-term fluctuations.
TheformulaforcalculatingtheSMAisgiveninEquation1.
S +S +···+S
t t−1 t−(n−1)
SMA = (1)
n
In the equation above, S represents the current value (e.g., the closing price on
t
day t) and S ,S ,...,S represent the values from previous periods within the
t−1 t−2 t−(n−1)
calculationwindow.
The EMA, unlike the SMA, assigns greater weight to more recent prices, which
makes it more sensitive and responsive to market changes. The formula for calculating
an EMA is represented in Equation 2. In the following equation, P(t) represents the
sequenceofobservationsovertimet(e.g.,closingprice,bandwidth,ordisplacement),and
α (alpha) is the smoothing coefficient, calculated as 2/(N +1), where N is the number
ofobservationsconsideredintheperiod. SmallervaluesofN resultinalargerα,making
theEMAmoresensitivetoslightvariationsintheobservedsamples[Vuetal. 2017].
EMA (t) = α·P(t)+(1−α)·EMA (t−1) (2)
x x
The RSI stands out as one of the most prominent and widely used technical in-
dicatorsintechnicalanalysisbytradersandinvestors[KulshresthaandSrivastava2020].
Developed by J. Welles Wilder Jr. [Wilder1978], the indicator’s primary function is to
measurethemagnitudeofrecentpricechangestoevaluateoverboughtoroversoldcondi-
tions for a given asset. The RSI has the following capabilities: (a) identifying potential
trend reversal points; (b) measuring the strength of the momentum; (c) adapting to differ-
enttimehorizons;and(d)havingwideacceptanceandsupportinacademicstudies.
The general formula for calculating the RSI is illustrated in Equation 3. The vari-
able RS (Relative Strength) represents the ratio of the average gains to the average losses
over a given period n. In this context, n corresponds to the number of time units consid-
ered(e.g.,days,ifthetimeframeisdaily). Theresultingvaluerangesfrom0to100.

(cid:20) (cid:21)
100
RSI(n) = 100− (3)
1+RS(n)
Wilder’s classic interpretation defines the RSI as follows: (a) “overbought” when
thevaluesurpasses70. Thismayindicatethattheassetisovervaluedanddueforabearish
reversal, signaling a selling opportunity; and (b) “oversold” when the value falls below
30. Thismayindicatethattheassetisundervaluedandabouttoundergoabullishreversal,
signalingabuyingopportunity.
2.4. NegotiationApproachesintheFinancialMarket
Predictingmarkettrendsandfinancialassetpricesposesaconstantchallengeforinvestors
and researchers. Throughout history, various approaches have been developed with the
objective of understanding and profiting in these markets, which can be broadly catego-
rizedintotraditionalmethodsand,morerecently,quantitativemethods.
2.4.1. TraditionalNegotiationMethods
Traditionaltradingmethodsrelyheavilyonhumananalysisandjudgment,whichareoften
subjecttoemotionsandbiases[Maetal. 2022]. Amongthemostwidelyusedapproaches
arefundamentalanalysisandtechnicalanalysis. Pateletal. [Pateletal. 2015]emphasize
that fundamental analysis entails a detailed examination of a company’s/country’s finan-
cial and economic situation. In contrast, technical analysis focuses on the retrospective
investigation of historical data, including an asset’s price fluctuations over time and its
associatedtransactionvolume.
2.4.2. QuantitativeTrading
Since the 1970s, quantitative trading (QT) has been a topic of interest in both academia
and the financial industry [Sunetal. 2023]. QT represents a paradigm shift in how in-
vestment decisions are made, using mathematical models, statistical methods, and com-
putational technology to identify investment opportunities and execute trades automati-
cally [Zhang2023]. QT offers a series of significant advantages compared to traditional
tradingapproaches,whichdriveitsgrowingadoptionintheglobalfinancialmarket. These
advantages include: (1) objectivity and discipline, (2) large-scale data processing capa-
bility,and(3)reductionofinformationasymmetry.
2.5. AlgorithmicTrading
Alsoknownasautomatedtradingoralgo-trading,thistechniqueusescomputerprograms
and algorithms to execute trades in the financial markets [Ansarietal. 2024]. This ap-
proach emerged as an alternative to the challenges associated with manual trading and
the variability of traditional approaches, aiming to enhance precision and efficiency in
financial operations [Ismailetal. 2022]. Such systems utilize computer programs to pro-
cesslargevolumesofdataandexecutetradingordersautomatically,basedonpre-defined
algorithms and parameters [ZhangandKhushi2020]. One of the primary advantages of
algorithmictradingisitsabilitytooperatecontinuously,reactingpromptlytomarketfluc-
tuations, without requiring continuous supervision from a human operator. Algorithmic

trading also offers the following advantages: (1) elimination of human emotions and bi-
ases, (2) speed and precision, (3) pattern detection, and (4) greater discipline and consis-
tency.
2.6. EvaluationMetrics
The validation of automated strategies requires the integrated consideration of return,
risk, and risk-adjusted metrics, since each group provides a distinct and complementary
perspective on the strategy’s performance. In this context, return metrics are widely used
to measure the profitability and consistency of strategies over time. Risk metrics, in turn,
areessentialforquantifyingmaximumlossesandmeasuringriskexposure.
To identify the primary metrics used in the evaluation of automated trading sys-
tems, a complementary study was conducted by these researchers [Cordeiroetal. 2025].
In that study, the primary metrics identified were: Annualized Return (AR), Cumulative
Return (CR), Maximum Drawdown (MDD), and the Sharpe Ratio. In addition to these
metrics, an extensive search in forums and the MQL5 language documentation led to the
identificationofthreesecondarymetricstobeconsideredintheevaluationprocess: Profit
Factor (PF), Expected Payoff (EP), and Recovery Factor (RF). Technical details about
thesemetricsarepresentedinSection4.4.
3. Related Work
In recent decades, a growing number of studies have focused on investigating compu-
tational techniques for modeling and automating trading strategies. The approaches ex-
ploredrangefromclassictechniques,suchasMachineLearning(ML)andArtificialNeu-
ral Networks (ANN), to more sophisticated methods, including Deep Neural Networks
(DNN),ConvolutionalNeuralNetworks(CNN),ReinforcementLearning(RL),andDeep
ReinforcementLearning(DRL).
In their research on the development of profitable trading strategies, Povitukhin
and Karmanova [PovitukhinandKarmanova2020] proposed a methodology that inte-
grates technical analysis indicators with ML algorithms, applied to the foreign exchange
market. The work is based on the premise that traditional trading systems, which rely
exclusively on technical indicators, often yield unsatisfactory financial results due to the
inherent lag of these indicators, which cannot keep up with real-time price movements.
To overcome this limitation, the authors frame day trading as a classification problem to
predict“buy”or“sell”signalsatthebeginningofeachday. Thestudy’scentralapproach
isbasedontheuseofsupervisedlearning,inwhichtheauthorsintroducetheconceptofa
“teacher”. This “teacher” corresponds to an idealized model designed to generate stable,
low-noisetradingsignals. Oneofthestudy’smostrelevantinsightsisitscritiqueofaccu-
racy as the sole metric for evaluating a trading system’s effectiveness. The authors argue
that the accurate measure of success is profitability, calculated in pips, because even if a
system has high accuracy in predicting signals, it may still not be profitable due to the
magnitudeofthepricemovements.
Despite the pertinent critique of the isolated use of accuracy, the success metric
adopted by the authors is, in itself, incomplete, as it disregards a fundamental factor:
risk. The study bases its evaluation solely on Cumulative Return (CR). This approach is
inadequate,asitcompletelyignoresrisk. Astrategycanshowahighcumulativereturnbut

with unacceptable risk (massive drawdowns), making it unfeasible in practice. Although
the authors critique the isolated use of accuracy and argue for profitability as a more
suitablemeasureofsuccess,theydonotmeasuretheriskassociatedwiththatprofitability.
Luangluewut and Thiennviboon [LuangluewutandThiennviboon2023] present a
distinct approach to trend prediction in the Forex market, proposing the conversion of
price time series into images for processing by a CNN. The experimental results demon-
strated the model’s high effectiveness, as it achieved an accuracy of 93% in predicting
trendsonthetestset. Inadditiontothepredictiveevaluation,theauthorsconductedtrad-
ing simulations with a simple algorithm to investigate the practical applicability of the
model as a trend indicator. In the scenarios tested, the proposed model achieved returns
between 6% and 422% higher than those achieved with traditional technical indicators.
This demonstrates the promising potential of treating time series as images for trend pre-
dictionintheForexmarket. However,similartothestudybyPovitukhinandKarmanova
[PovitukhinandKarmanova2020], the strategy’s evaluation is based solely on cumula-
tivereturn. Thisapproachisinadequate,asitcompletelyignoresrisk.
Inacomplementaryapproach,Chinprasatsaketal. [Chinprasatsaketal. 2020]fo-
cused on predicting the daily high and low prices in the foreign exchange market, specif-
ically for the EUR/USD pair. To achieve this, they compared various artificial neural
network architectures, including traditional models and the variants they proposed. A
central contribution of the work is the evaluation of the forecasting models not through
standard error metrics, but through a trading simulation system that measures investment
effectiveness in terms of “Total Return” and “Drawdown”. The main innovation of the
proposedmodelsbytheauthorsliesintheuseofEmpiricalModeDecomposition(EMD).
This process separates the original time series into multiple simpler components, known
asIntrinsicModeFunctions(IMFs). Thenetwork’soutputconsistedoftwonumbers: the
forecast for the current day’s high and low prices. The results of the trading simulation
demonstrated that the proposed models significantly outperformed the baseline models.
Finally,theauthorsconcludedthatEMD’sabilitytoextractrelevantinformationfromthe
signalsignificantlyimprovedtheperformanceoftheneuralnetworks.
Expanding on the application of artificial intelligence in the financial market,
Chantonaetal. [Chantonaetal. 2020]addressafundamentallimitationofReinforcement
Learning(RL)modelsappliedtotrading. Theauthorsarguethatmosttradingsystemsex-
isting up to 2020, based on RL, exclusively used historical technical data (such as prices
andindicators)asthestateinputforthedecision-makingagent. Toovercomethisgap,the
authors propose a hybrid model that enables the trading agent to process and understand
bothtechnicalandfundamentaldataintheformofnewsheadlines. Theproposalisbased
ontheuseofDRLtechniques,specificallytheDeepRecurrentQ-Network(DRQN)archi-
tecture, combined with Recurrent Convolutional Neural Networks (RCNN), Word2Vec,
andLongShort-TermMemory(LSTM).Performancewasmeasuredusingfinancialmet-
rics,includingNetProfit,AnnualizedReturn,theSharpeRatio,theUlcerPerformanceIn-
dex, and Maximal Drawdown. The results demonstrated that the proposed model, which
combines technical and fundamental data (named Mix Data), outperformed those that
usedonlytechnicaldata.
Inanapproachfocusedonthecompleteautomationofthetradingprocess,Ismail
et al. [Ismailetal. 2022] developed an automated system to predict movements in the

foreign exchange market. The main objective of the work was to eliminate the human
emotional factor that often leads manual traders to significant losses. To achieve this, the
authorsproposeastrategythatcombinesTechnicalAnalysis(TA)indicatorsandanANN
to create a system that operates independently on the MetaTrader 4 (MT4) platform. The
performance of the optimized EA was validated through a five-year backtest simulation
(from 2017 to 2022). The simulation demonstrated that the system was able to gener-
ate profit consistently, turning an initial balance of 10 dollars into 185.43 dollars, which
proves the viability of the proposed approach. The study concludes that the adoption of
ANN-based strategies, when combined with carefully selected technical indicators, can
provide significant advantages in predicting market trends and automating trading strate-
gies.
Taken together, the works by Chinprasatsak et al. [Chinprasatsaketal. 2020] and
Chantona et al. [Chantonaetal. 2020] represent an advancement in their analyses by
incorporatingMaximumDrawdown(MDD)alongsidereturnmetrics. However,theeval-
uation remains incomplete, as the absence of risk-adjusted metrics, such as the Sharpe
Ratio, limits the assessment of the quality of these returns. Thus, it is not possible to de-
terminewhethertheprofitsresultedfromanefficientstrategyorsimplyfromexposureto
excessive risk. The work by [Ismailetal. 2022] also presents a similar limitation, focus-
ing only on return metrics (AR and CR), despite its objective being to create a profitable
EA.
AddressingthecomplexityofMLmodels,theresearchbyAloud[Aloud2020]in-
vestigatestheroleoffeatureselectioninthedevelopmentofafinancialtradingsystem. To
achieve this, the author proposed a methodology for a multi-agent Deep Artificial Neural
Network (D-ANN) system, in which multiple input features – such as technical analysis
indicators,intradayseasonality,andfundamentalanalysis–actasindividualagents,each
providing a trading recommendation: buy, sell, or hold. The central innovation of the
study lies in how the recommendations from these agents are combined. Instead of as-
signingequalweightstoallfeatures,theauthorusesaGeneticAlgorithm(GA)toevolve
andoptimizetheweightsofeachinput.
This process allows the system to learn, over iterations, which agents are more
effective and, therefore, should exert greater influence on the final trading decision. The
results showed that the D-ANN system outperformed all other strategies, achieving the
highest average return and the highest Sharpe Ratio. This study employs a peculiar eval-
uation approach, relying solely on the Sharpe Ratio. Although it is a powerful metric for
evaluatingrisk-adjustedreturn,itsuseinisolationisproblematic,asitdoesnotinformthe
investoraboutthemagnitudeofpotentiallossesoroperationalefficiency(PF).Astrategy
can exhibit a good Sharpe Ratio but still have an unacceptable drawdown from both a
psychologicalandfinancialstandpointforaninvestor.
Table1comparestheanalyzedstudiesbasedonthemetricsdefinedinSection2.6
anddiscussedindetailinSection4.4. Thecolumnheadingsforthetableare: Annualized
Return(AR),CumulativeReturn(CR),MaximumDrawdown(MDD),ProfitFactor(PF),
Expected Payoff (EP), and Recovery Factor (RF). The purpose of this comparison, in
additiontocontextualizingthe’ProposedSolution,’istoidentifytheperformancemetrics
used to evaluate each of the approaches documented in the literature. This initial survey
is essential for conducting a subsequent comparative analysis to assess the effectiveness

androbustnessoftheproposedsolutionagainstothers.
|                                  | Work/Metrics |                                   | AR  | CR  | MDD Sharpe | PF  | EP RF |
| -------------------------------- | ------------ | --------------------------------- | --- | --- | ---------- | --- | ----- |
| [PovitukhinandKarmanova2020]     |              |                                   | No  | Yes | No No      | No  | No No |
| [Chinprasatsaketal.              |              | 2020]                             | Yes | Yes | Yes No     | No  | No No |
| [Chantonaetal.                   |              | 2020]                             | Yes | Yes | Yes Yes    | No  | No No |
| [Aloud2020]                      |              |                                   | No  | No  | No Yes     | No  | No No |
| [Ismailetal.                     | 2022]        |                                   | Yes | Yes | No No      | No  | No No |
| [LuangluewutandThiennviboon2023] |              |                                   | No  | Yes | No No      | No  | No No |
|                                  |              | Table1. ComparisonbetweentheWorks |     |     |            |     |       |
As can be observed in Table 1, the works discussed in this section present signif-
icant methodological gaps by neglecting one or more essential evaluation metrics, which
limitsthevalidityandrobustnessoftheirautomatedtradingstrategies. Incontrast,Scalper
Major, by employing an evaluation framework that provides a balanced integration of re-
turn,risk,andrisk-adjustedmetrics,offersamuchmorecompleteandreliableanalysisof
itsperformance.
| 4. Proposed | Solution |     |     |     |     |     |     |
| ----------- | -------- | --- | --- | --- | --- | --- | --- |
Having established the theoretical foundation, the related works, and the relevance of the
problem, this section is dedicated to detailing the proposed solution and the criteria for
its evaluation. First, the architecture of the proposed system is described, detailing its
design and operation. Next, the adopted strategies for managing new trades when the
market moves against already open positions and for scaling the lot size are presented.
Finally, a systematic survey of the most commonly used financial evaluation metrics in
the literature is presented, which not only guides the analysis of the results of this study
butalsoestablishesitselfasareferenceforfutureresearchinthearea.
4.1. ScalperMajorArchitecture
Scalper Major is an automated trading system developed to operate in the Forex mar-
ket, implementing short-term strategies with minimal human intervention. It was imple-
mented using the MQL5 programming language, which is native to the MetaTrader 5
platform. The system’s operation is based on a set of rules derived from technical crite-
ria (the signal processor), combined with a strict risk and money management system, as
outlinedinthearchitecturepresentedinFigure1.
Scalper Major
| Technical Signal Heuristic |     | Technical Criteria (RSI, SMA) |     |     |     |     |     |
| -------------------------- | --- | ----------------------------- | --- | --- | --- | --- | --- |
Signal
|     |     |     |     | Processor | Market Data (OHLC) |     |     |
| --- | --- | --- | --- | --------- | ------------------ | --- | --- |
Candlestick Identification
Candlestick Pattern (Marubozu)
|                 | Heuristic |                                 |          | Input Signal |                                     |               |        |
| --------------- | --------- | ------------------------------- | -------- | ------------ | ----------------------------------- | ------------- | ------ |
|                 |           | R i s k  P a ra m et e r s      | R is k   |   T r a d    | e  A p p ro ve d                    |               |        |
|                 |           | (D r a w d o w n , M a r g i n) |          | ( A c c      | e p ta b le  R is k ) C a p it a l  | Opening Order |        |
| Risk Heuristics |           |                                 | Ma n a g | er           | M a n a g e r                       |               | Broker |
Lot Sizing Rules
Capital Heuristics
|     |     | Figure1. | ScalperMajorArchitecture. |     |     |     |     |
| --- | --- | -------- | ------------------------- | --- | --- | --- | --- |

4.1.1. SignalProcessor
The operational flow of Scalper Major begins with the receipt of market data (OHLC
– open, high, low, close) provided by the broker. This data is directed to the Signal
Processor(SP),thefirstcomponentinthedecision-makingprocess. TheSPevaluatesthe
feasibility of a new trade using two main heuristics, analyzed at the beginning of each
new hour based on the newly closed H1 (1-hour) candle: the Technical Signals Heuristic
andtheCandlestickIdentificationHeuristic,whicharedetailedbelow.
• TechnicalSignalsHeuristic: Thisheuristicusesacombinationoftwoindicators,
the details of which are presented in Section 2.3: the RSI and the SMA. During
the testing phase, it was found that the best buy signals were generated when the
RSIwasbelow30,whilethebestsellsignalsoccurredwhenitwasabove70. Fur-
thermore, it is required that the closing price of the candlestick be at a significant
distance from the 20-period Simple Moving Average (SMA-20): below it for buy
trades and above it for sell trades. Similar to the 30 and 70 levels for the RSI, the
SMA-20wasselectedbecauseityieldedthebestresultsinthetestsperformed. A
sharpdistanceofthepricefromthisaveragereinforcesthehypothesisofanexces-
sive extension of the downward or upward movement, increasing the probability
ofacorrection.
• Candlestick Identification Heuristic: This heuristic focuses on recognizing the
Marubozupattern,thecharacteristicsofwhicharedetailedinSection2.2. During
the testing phase, the combination of this pattern with the RSI was found to be
a robust confirmation for trade entries. A sell signal is generated when a bullish
MarubozuoccurswiththeRSIinanoverboughtcondition(above70),indicatinga
likelyexhaustionoftheuptrend. Ontheotherhand,abuysignalisgeneratedwhen
abearishMarubozuisidentifiedwiththeRSIinanoversoldcondition(below30).
Figure 2 presents an example of a sell trade executed on the EURUSD asset. It is
observedthattheRSIofthecandlepriortotheselltradeisabove70. Furthermore,
it is noted that this same candle closed at a considerable distance from the SMA-
20 (the white line below the candlesticks). These two conditions, combined with
thebullishMarubozu,resultedinasuccessfulselltrade.
Figure2. Exampleofaselltrade.

4.1.2. RiskManager
Once both of the SP’s heuristics indicate a trading opportunity, the Risk Manager (RM)
is triggered. This component acts as a safety filter, applying the Risk Heuristic to evalu-
ate the strategy’s sustainability and protect the capital from excessive losses. Its primary
function is to ensure that risk exposure remains within predefined and acceptable limits.
This heuristic considers data such as the available free margin and implements a maxi-
mumloss(drawdown)controlattwolevels: individual(perasset)andglobal. Anewtrade
on a specific asset is blocked if the open trades show a negative float greater than 10%.
Additionally, the system ceases to open any new trades if the overall account drawdown
(the sum of all floating losses) exceeds 25%. These 10% and 25% limits were set em-
pirically during the testing phase, aiming to strike an optimal balance between allowing
the strategy to operate without excessive restrictions while rigorously protecting capital.
It is essential to note that the Risk Manager’s decision takes precedence over that of the
SignalProcessor;thatis,eveniftheentryconditionsareperfectlymet,theoperationwill
be canceled if the Risk Heuristic indicates an exposure that exceeds the defined safety
parameters.
4.1.3. CapitalManager
AftertheoperationisvalidatedandapprovedbytheRM,controlistransferredtotheCap-
ital Manager (CM), the last component in the flow before the execution of a new trade
(position). TheCM’sprimaryresponsibilityistosizethelotfornewtrades,afundamen-
tal step in capital management. To achieve this, the CM employs the Capital Heuristic
to determine the optimal lot size. The lot size is automatically adjusted based on the risk
parameters defined in the EA and the total capital available in the account. This mecha-
nismensuresthattheexposureleveladaptstothegrowthordeclineoftheaccountequity,
promoting the scalability of returns in favorable scenarios and, crucially, capital preser-
vation during periods of loss, thereby avoiding disproportionate risk exposures. Unlike
the Risk Heuristic, which acts as a veto mechanism, the Capital Heuristic does not block
the trade. Finally, once the lot size is defined, the CM sends the request to open the new
position to the broker, completing the automated cycle. The joint application of these
criteria, from signal identification to capital sizing, allowed the implemented strategy to
achieve promising results in tests using historical data, as demonstrated and discussed in
Section5.
4.2. TradingandRecoveryStrategy
However, if the market moves against the initial position, the EA activates a recovery
mechanism that combines the grid and martingale strategies. The grid strategy consists
of opening new positions at predefined price intervals as the market moves against the
original position. The martingale strategy, in turn, involves increasing the lot size of the
subsequent trade. Nevertheless, its isolated use is high-risk. To circumvent this danger,
Scalper Major adopts a hybrid and innovative approach. Before applying the martingale,
the system opens two consecutive positions with the same lot size, then doubles the lot
size. For example, the lot sequence would follow the pattern 0.01, 0.01, 0.02, 0.02, 0.04,
0.04,andsoon,untilthemaximumnumberofopenablepositionsisreached.

Furthermore,aneworderinthegridisopenedonlyiftheSPidentifiesanewvalid
entry signal, according to the criteria already detailed. This prevents the indiscriminate
opening of positions that occurs in pure martingale systems. Additionally, to limit risk
exposure, a maximum of 14 simultaneously open trades has been set per asset for each
direction (14 buy and 14 sell). When the grid and martingale system are active, the profit
target is met when the total profit of the winning positions reaches a value three times
greater than the accumulated loss of the losing positions, ensuring a favorable risk-return
ratiofortherecovery. Weemphasizethattheparametersmentionedinthissectionarenot
derivedfromcurvefittingbutratheraredefinedasoperationalsafetyconstraints.
4.3. LotSizingModelwithProgressiveRebalancing
The logic for the dynamic calculation of the lot size is formalized through a series of
equations presented below. These equations adjust the trading volume based exclusively
ontheaccount’saccumulatedhistoricalprofit,P .
h
4.3.1. RebalancingFactorCalculation(Q )
b
Equation 4, presented below, indicates the number of times that the historical profit (P )
h
has surpassed the rebalancing threshold R. The factor Q is an integer that represents the
b
numberofrebalancingevents.
|     | (cid:22) | P (cid:23) |     |     |     |
| --- | --------- | ---------- | --- | --- | --- |
h
|     |    | ,   | seR > | 0   |     |
| --- | --- | --- | ----- | --- | --- |
|     | Q = | R   |       |     | (4) |
b
0,
|     |     |     | seR ≤ | 0   |     |
| --- | --- | --- | ----- | --- | --- |
4.3.2. AdjustmentofReferenceCapitalBase(B′)
x
B
The initial reference base capital, x , which represents the amount of profit required
to justify each increment of the base lot, is adjusted based on the factor Q . For each
b
rebalancing event, a constant C = 1000 is added to the base capital, making the criterion
foralotincreasestricter. Equation5showshowthiscriterioniscalculated.
|     | B′ = | B +(C | ·Q ) |     | (5) |
| --- | ---- | ----- | ---- | --- | --- |
|     | x    | x     | b    |     |     |
4.3.3. CalculationofFinalLotSize(L)
Finally, the final lot size to be returned by the variable L is calculated, as represented in
Equation 6. The equation determines how many multiples of the adjusted base capital
(B′) are contained within the historical profit (P ). This result is then multiplied by the
x h
base lot size corresponding to B , L (e.g., 0.01). The use of the floor function (⌊·⌋)
|     | x base |     |     |     |     |
| --- | ------ | --- | --- | --- | --- |
ensuresthatthelotisonlyincrementedaftertheprofithasfullycoveredthenewthreshold.
|     |     | (cid:22) (cid:23) |     |     |     |
| --- | --- | ----------------- | --- | --- | --- |
|     |    | P                 |     |     |     |
h
|     | L   | ·   | , seP | ≥ B′ |     |
| --- | ---- | --- | ----- | ---- | --- |
| L = | base | B′  | h     | x    |     |
(6)
x
|     | 0, |     | seP | < B′ |     |
| --- | --- | --- | --- | ---- | --- |
h
x

The principle of Scalper Major’s lot scaling method is based on the premise that
the trading volume should be a function directly proportional to the accumulated profit.
This non-linear scaling approach, triggered by the rebalancing threshold R, makes the
system progressively more conservative: as profits increase, the capital requirement for
thenextlotincrementalsogrows. Fromariskmanagementperspective,thismethodology
aimstomitigatetheimpactoflargedrawdownsthatcanoccurafterperiodsofsignificant
profit.
4.4. FinancialAssessmentMetrics
Next, each metric used for evaluating the strategy’s performance will be detailed. It is
crucialtohighlightthattheconsolidationofthesemetricsistheresultofanextensiveand
complexsurveyconductedinthespecializedliterature.
• AnnualizedReturn(AR):Representsthecompoundgrowthrateofaninvestment
overoneyear. Itisanessentialmetricforevaluatingthelong-termperformanceof
a strategy, allowing direct comparisons across different periods and asset classes,
evenwhenreferringtodistinctinvestmenthorizons[Huangetal. 2024].
• Cumulative Return (CR): Represents the percentage change in capital from the
beginningoftheinvestmenttothepresentmoment[Huangetal. 2024]. Thismet-
ric is widely used to measure the total profitability of an investment or trading
strategy over a specific time horizon [Lietal. 2024]. A high cumulative return
may indicate significant growth of the invested capital, but it does not necessarily
reflectthestabilityofthegains.
• Maximum Drawdown (MDD): Measures the maximum observed loss from
the peak value of an investment or strategy to its lowest point before
a recovery [ShahsafiandNaderkhani2024]. It is also often interpreted as
the maximum exposure to risk or the most significant possible capital loss
[OlorunsheyeandMeenakshi2024]. Thismetricisessentialforassessingtherisk
associated with a trading or investment strategy [Rahimpouretal. 2024], as it re-
veals the magnitude of losses during adverse market periods. Strategies with a
high MDD may be considered riskier, as they require significant recovery to re-
turntotheirpreviouslevel.
• Sharpe Ratio: Evaluates the risk-adjusted return of an investment or trading
strategy [Rahimpouretal. 2024]. It helps investors interpret risk-adjusted per-
formance[Lietal. 2019]bymeasuringtheexcessreturnobtainedperunitofrisk
taken and is widely used to assess the effectiveness of trading strategies. Values
greater than 1 indicate a more favorable risk-return relationship for the strategy
[Cartaetal. 2021], which is why traders extensively use it to evaluate the effi-
ciencyoftradingsystems[Blazˇiu¯nasandRaudys2019].
• Profit Factor (PF): According to the MQL5 documentation5, the PF can be un-
derstood as the ratio of gross profit to gross loss, where a value of 1 indicates
that the sum of profits is equivalent to the sum of losses. Huang and Martin
[HuangandMartin2019] explains that the PF, which can be understood as the
annualized rate of return per unit of risk, is a crucial metric for evaluating the
performanceofleveragedtradingstrategies.
5MQL5Documentation: https://www.mql5.com/pt/docs

• Expected Payoff (EP): The MQL5 documentation defines EP as a statistical
indicator that represents the average profit or loss per trade. For Qin and Li
[QinandLi2011], EP is a practical tool for evaluating and comparing trading
strategies in scenarios of uncertainty, offering a way to quantify expected out-
comesevenwhenhistoricaldataisscarceorinadequate.
• Recovery Factor (RF): According to the MQL5 documentation, the RF is an
indicatorthat reflects thestrategy’srisklevel, representingtheamountthe system
is willing to risk to obtain a profit. Nasution et al. [Nasutionetal. 2024] points
out that values above 1 indicate that the EA has good recovery capability, while
valuesbelow0.3revealthattheEAhasdifficultyovercomingtheDrawdown.
Incomparisonwithrelatedworksintheliterature,theproposedsolutionaddresses
recurring limitations in previous approaches, including the lack of risk-related indicators
and the lack of transparency in money management. By integrating a realistic empirical
evaluation with a comprehensive set of metrics, Scalper Major represents an advance-
ment in the state of the art of automated trading, making a significant contribution to the
developmentofcomputationaltoolsthatsupportdecision-makinginthefinancialmarket.
5. Results and Discussions
This section presents the results achieved by Scalper Major in a controlled (simulated)
environment. Scalper Major was developed using Quantitative Trading techniques (de-
tailed in Section 2.4.2) and was configured to operate specifically on the currency pairs
EUR/USD, GBP/USD, USD/CAD, and USD/CHF. The selection of these assets was
based on the results obtained from tests conducted on 24 currency pairs, with an aver-
age duration of 8 hours per asset. During the evaluation process, the metrics discussed in
Section4.4weretakenintoconsideration.
The EA’s backtesting period corresponds to the interval between January 2016
and December 2023. This period was methodologically chosen to subject the proposed
strategy to various market conditions. The inclusion of these distinct scenarios aims to
validatethestrategy’srobustnessandgeneralizationcapability,evaluatingitsperformance
notonlyinfavorablemarketconditionsbutalsoduringperiodsofstressandsystemicmar-
ket uncertainty. These events include: (1) the Brexit referendum and the US presidential
elections of 2016 and 2020, (2) the global COVID-19 health crisis, which catalyzed one
of the fastest bear markets in history, (3) the start of the war in Ukraine, with consequent
stress on commodity markets, and (4) the subsequent abrupt transition from an environ-
ment of expansionary monetary policy to a restrictive cycle of quantitative tightening to
combatglobalinflation.
To better approximate the results to real market conditions, the following factors
were considered: (a) a commission rate of 7 dollars per lot, (b) an exemption from the
swap fee (although it is common for some brokers to charge it), and (c) an execution de-
lay of 50 ms. In the simulation process, an initial capital of $20,000.00 was used, and
the system achieved a total net profit of $751,533.23, resulting from a gross profit of
$1,060,523.23 and gross losses of $308,991.00, which include trades closed with a nega-
tivebalanceandcommissions. Intotal,11,571tradeswereexecuted,ofwhich7,217were
long (buy) trades and 4,354 were short (sell) trades. The overall win rate was 82.54%,
withan83.66%rateforlongtradesandan81.42%rateforshorttrades.

Figure3presentsthegroupeddistributionofthetradesmadeineachmonthofthe
analyzedyears. Arelativelyuniformdistributionisobserved,withvaluesvaryingapprox-
imately between 800 and 950 entries. The month of March stands out, with the highest
number of entries, overtaking the 900 mark, while April recorded the lowest quantity,
showing a slight decrease compared to the other months. Figure 4 presents the monthly
distributionofprofitsandlossesthroughouttheanalyzedperiod,enablingamoredetailed
analysisofseasonalityandfinancialperformancepatterns. Itisobservedthatprofits,rep-
resente human performance is often compromised by emotionald by the blue bars, con-
sistently exceed losses, indicated by the red bars, in all analyzed months. The months of
May,June,andJulystandoutasthosewiththehighestprofitability,withanabsolutepeak
recorded in June, when profits surpassed $130,000.00. On the other hand, the months of
FebruaryandDecemberrecordedthelowestprofit.
1000 Profits Losses
e s 800 120k
ri
nt
)
100k
E 600 $
of s ( 80k
b
e r 400 oll a
r
60k
m D 40k
u
N 200
20k
0 0
Jan Feb Mar AprMayJun Jul AugSep Oct NovDec Jan Feb Mar AprMayJun Jul AugSep Oct NovDec
Month Month
Figure3. NegotiationsperMonth. Figure4. ProfitsandLosses.
Figure 5 presents the risk graph, in which the blue line represents the account’s
growth, and the green line represents the drawdown. The graph also demonstrates robust
andconsistentgrowthovertime,underscoringtheeffectivenessofthestrategy. Anotable
point in the trading history occurred in July 2023, when the system experienced its most
significantdrawdown,reachingavalueof9.43%. Thecurvealsoshowsthat,immediately
after this setback, the system not only reversed the losses but also quickly resumed its
upward trajectory, continuing to generate new profits, which attests to the soundness and
recoverycapabilityoftheemployedstrategy.
Figure5. RiskandRobustness.
Table2presentsananalysisofScalperMajor’sperformanceincomparisontothe
works presented in Section 3, using the metrics made available in the respective studies.

The data presented demonstrate that the results of Scalper Major are notably superior
across most of the analyzed metrics. The most significant indicator is the Cumulative
Return (CR), which reached $751,533.23 from an initial deposit of $20,000.00. This
superiority is also reflected in the risk-adjusted return metric. The Sharpe Ratio of 1.63
isthehighestamongthestudiesthatreportedit. Thissuggeststhatthestrategywasmore
efficientatgeneratingreturnsforeachunitofriskassumed.
Additionally, its win rate of 82.82% is among the highest, highlighting its robust
operationalconsistency. AlthoughtheworkofIsmailetal.[Ismailetal. 2022]presentsa
higherAnnualReturn(AR)(79.32)thanScalperMajor(57.87),thestudydoesnotreport
the Maximum Drawdown (MDD) of its strategy. The absence of the MDD seriously
compromisesthevalidityofthepresentedresults,asahighreturnmayhavebeenachieved
atthecostofaveryhighandpotentiallyunacceptableriskforaninvestor. ScalperMajor,
on the other hand, presents an MDD of 9.43%, offering complete transparency about its
risk. Although not listed in Table 2, other relevant data include: the Profit Factor of 3.43,
theExpectedPayoffof64.95,andtheRecoveryFactorof11.47.
Work/Metrics Deposit($) CR($) AR(%) MDD(%) Sharpe Accuracy(%)
ScalperMajor 20.000,00 751.533,23 57,87 9,43 1,63 82,82
PovitukhinandKarmanova - 1.171,15 - - - 70,0
Chinprasatsaketal. 10.000,00 2.925,00 9,75 7,72 - -
Chantonaetal. 21.200,00 71.182,62 11,64 3,67 1,26 -
Aloud - - - - 0,42 68,5
Ismailetal. 10,00 175,43 79,32 - - 79,7
LuangluewutandThiennviboon - 76.713,37 - - - 93,0
Table2. ScalperMajorvsOtherWorks
Other important data worth highlighting are as follows: (a) the best trade resulted
inaprofitof$15,948.80,whiletheworsttradegeneratedalossof-$1,890.00;(b)themax-
imumnumberofconsecutivewinswas7,whilethemaximumforconsecutivelosseswas
2;and(c)themostsignificantlossfromalosingstreakwas-$8,587.32,whilethemostsig-
nificant profit from a winning streak was $27,165.33. In general, the risk was adequately
managed, and the system maintained a high level of consistency, even in the face of
chaoticevents. Additionaldatanotpresentedinthisarticlecanbeaccessedthroughthere-
portavailableatthefollowinglink: https://zenodo.org/records/16983868.
At the same link, the EA is available, along with the instructions on how to replicate the
results.
The results discussed in this section highlight the robustness and consistency of
ScalperMajorinasimulatedenvironment,demonstratingsignificantperformanceinboth
profitability and risk control. The financial metrics presented indicate the system’s effi-
ciency in capturing market opportunities while simultaneously mitigating losses. These
findings, although promising, will be further explored in future analyses, with a focus on
validation in live environments and on the evaluation of aspects related to adaptation to
differentmarketconditions.
6. Conclusion
This work presents Scalper Major, an automated trading system (Expert Advisor) de-
signed to operateefficiently andconsistently inthe Forexmarket, anenvironment known

for its high volatility and complexity. The proposed solution stands out for its robust,
modular architecture, which cohesively integrates technical and managerial heuristics to
identify opportunities with strict risk and capital control. The main contributions of this
researcharemultifacetedandrepresentasignificantadvancementinthefieldofalgorith-
mic trading. First, the work provides an unpublished compilation of the main evaluation
metrics used in the literature for trading systems, serving as a benchmark for future re-
search. Second, it develops a set of specialized heuristics for identifying opportunities
and executing orders, combined with strict risk control and money management. Finally,
it presents a functional implementation of the proposed architecture, validated through
extensivesimulationswithhistoricaldata.
The results obtained and consolidated in Table 2 demonstrate the notable superi-
ority of Scalper Major in comparison to other solutions in the literature. The strategy’s
robustnesswasvalidatedthroughanextensivebacktestingperiod,spanningfromJanuary
2016toDecember2023,whichincludedhigh-impacteventsandvariousmarketregimes,
such as the COVID-19 crisis and the war in Ukraine. This validation under adverse con-
ditions demonstrates the system’s generalization capability and soundness, reinforcing
the results presented and consolidated in Table 2, which show the notable superiority
of the proposed solution compared to others in the literature. In summary, Scalper Ma-
jor not only proves to be a profitable and risk-managed tool in a simulated environment
but also contributes significantly to the state of the art by establishing a new standard of
methodological rigor and transparency in the evaluation of automated trading systems.
The promising results pave the way for future research, including validation in a live
environmentandadaptationtodifferentmarketconditions.
References
Almeida, L. and Vieira, E. (2023). Technical analysis, fundamental analysis, and
ichimokudynamics: Abibliometricanalysis. Risks,11(8).
Aloud, M. E. (2020). The role of attribute selection in deep anns learning framework
for high-frequency financial trading. Intelligent Systems in Accounting, Finance and
Management.
Ansari, Y., Gillani, S., Bukhari, M., Lee, B., Maqsood, M., and Rho, S. (2024). A multi-
facetedapproachtostockmarkettradingusingreinforcementlearning. IEEEAccess.
Blazˇiu¯nas,S.andRaudys,A.(2019). Comparativestudyofneuralnetworksanddecision
trees for application in trading financial futures. In 2019 International Conference on
DeepLearningandMachineLearninginEmergingApplications(Deep-ML).
Bordo, M. (1993). The gold standard, bretton woods and other monetary regimes: An
historicalappraisal. WorkingPaper4310,NationalBureauofEconomicResearch.
Caffentzis, C. G. (2001). Hume, money, and civilization; or, why was hume a metallist?
HumeStudies.
Carta, S. M., Consoli, S., Podda, A. S., Recupero, D. R., and Stanciu, M. M. (2021).
Ensembling and dynamic asset selection for risk-controlled statistical arbitrage. IEEE
Access.

Chantona,K.,Purba,R.,andHalim,A.(2020). Newssentimentanalysisinforextrading
using r-cnn on deep recurrent q-network. In 2020 Fifth International Conference on
InformaticsandComputing(ICIC).
Chinprasatsak,K.,Niparnan,N.,andSudsang,A.(2020). Neuralnetworkforforecasting
highpriceandlowpriceonforeignexchangemarket. In202017thInternationalCon-
ferenceonElectricalEngineering/Electronics,Computer,TelecommunicationsandIn-
formationTechnology(ECTI-CON).
Cordeiro, J. J. R., de Arau´jo, A. H. M., and Avelino, G. A. (2025). Beyond profit: An
analysisofriskandreturnmetricsinautomatedtradingsystems. InProceedingsofthe
Brazilian Conference on Intelligent Systems (BRACIS), Fortaleza, CE, Brasil. To be
published.
El Mahjouby, M., Taj Bennani, M., Lamrini, M., Bossoufi, B., Alghamdi, T. A. H., and
ElFar,M.(2024). Machinelearningalgorithmsforforecastingandcategorizingeuro-
to-dollarexchangerates. IEEEAccess.
Heinz, A., Jamaloodeen, M., Saxena, A., and Pollacia, L. (2021). Bullish and bearish
engulfing japanese candlestick patterns: A statistical analysis on the s&p 500 index.
TheQuarterlyReviewofEconomicsandFinance.
Huang, Y., Zhou, C., Cui, K., and Lu, X. (2024). Improving algorithmic trading consis-
tencyviahumanalignmentandimitationlearning. ExpertSystemswithApplications.
Huang, Z. and Martin, F. (2019). Pairs trading strategies in a cointegration framework:
back-testedoncfdandoptimizedbyprofitfactor. AppliedEconomics.
Ismail,M.A.H.,Yasruddin,M.L.,Husin,Z.,andTan,W.K.(2022). Automatedtrading
systemforforecastingtheforeignexchangemarketusingtechnicalanalysisindicators
and artificial neural network. In 2022 IEEE 18th International Colloquium on Signal
Processing&Applications(CSPA).
Kulshrestha,N.andSrivastava,V.K.(2020). Synthesizingtechnicalanalysis,fundamen-
tal analysis & artificial intelligence – an applied approach to portfolio optimisation &
performanceanalysisofstockpricesinindia. In20208thInternationalConferenceon
Reliability,InfocomTechnologiesandOptimization(TrendsandFutureDirections).
Li, L., Liu, Q., Li, Y., Mu, Y., and Zhang, Z. (2024). A risk-sensitive automatic stock
trading strategy based on deep reinforcement learning and transformer. In 2024 IEEE
20thInternationalConferenceonAutomationScienceandEngineering(CASE).
Li,Y.,Zheng,W.,andZheng,Z.(2019). Deeprobustreinforcementlearningforpractical
algorithmictrading. IEEEAccess,7.
Luangluewut, W. and Thiennviboon, P. (2023). Forex price trend prediction using con-
volutional neural network. In 2023 20th International Conference on Electrical Engi-
neering/Electronics,Computer,TelecommunicationsandInformationTechnology.
Ma,R.,Ye,S.,Feng,Z.,andJin,J.(2022).Researchonquantitativetradingstrategybased
on lstm and dynamic programming. In 2022 International Conference on Computers,
InformationProcessingandAdvancedEducation(CIPAE).
Meltzer, A. H. (1991). Us policy in the bretton woods era. Federal Reserve Bank of St.
LouisReview.

Naranjo, R., Arroyo, J., and Santos, M. (2018). Fuzzy modeling of stock trading with
fuzzycandlesticks. ExpertSystemswithApplications.
Nasution,M.A.etal.(2024). Perancangandanpengujiankinerjaexpertadvisorberbasis
indikator rsi, ma, dan optimasi lot pada 10 pair forex populer dengan akun swap-free.
JurnalSains,Teknologi&Komputer.
Olorunsheye, A. O. and Meenakshi, S. (2024). Ai powered indicatorless algorithmic
trading bot for cryptocurrency and financial market. In 2024 International Confer-
ence on Emerging Technologies in Computer Science for Interdisciplinary Applica-
tions(ICETCS).
Patel, J., Shah, S., Thakkar, P., and Kotecha, K. (2015). Predicting stock and stock price
indexmovementusingtrenddeterministicdatapreparationandmachinelearningtech-
niques. Expertsystemswithapplications.
Povitukhin, S. and Karmanova, E. (2020). Development of a profitable trading strategy
with data mining techniques. In 2020 International Multi-Conference on Industrial
EngineeringandModernTechnologies(FarEastCon).
Qin, Z. and Li, X. (2011). Expected payoff of trading strategies involving european
optionsforfuzzyfinancialmarket. IranianJournalofFuzzySystems.
Rahimpour, S. M., Goudarzi, R., Shahparifard, V., and Mirpoorian, S. N. (2024). Al-
gorithmic trading using technical indicators and extereme gradient boosting. In 2024
11thIEEESwissConferenceonDataScience(SDS).
Shahsafi, S. and Naderkhani, F. (2024). Enhancing stock trading performance with deep
q-learning by addressing noisy data through advanced denoising techniques. In 2024
27thInternationalConferenceonInformationFusion(FUSION).
Sun, S., Wang, R., and An, B. (2023). Reinforcement learning for quantitative trading.
ACMTrans.Intell.Syst.Technol.
Varghese, A. A., Krishnadas, J., and Kumar, R. S. (2023). Candlestick chart based stock
analysis system using ensemble learning. In 2023 International Conference on Net-
workingandCommunications(ICNWC).
Vu, V.-H., Mashal, I., and and, T.-Y. C. (2017). A novel bandwidth estimation method
basedonmacdfordash. KSIITransactionsonInternetandInformationSystems,11(3).
Weithers, T. (2011). Foreign Exchange: A Practical Guide to the FX Markets. Wiley
Finance.Wiley.
Wilder,J.W.(1978). Newconceptsintechnicaltradingsystems. Greensboro,NC.
Zafeiriou, T. and Kalles, D. (2021). Ultra-short-term trading system using a neural
network-basedensembleoffinancialtechnicalindicators. NeuralComput.Appl.
Zhang, P. (2023). Research into developing a data mining-based quantitative trading
system for use with software and high performance computers. In 2023 International
ConferenceonIndustrialIoT,BigDataandSupplyChain(IIoTBDSC).
Zhang, Z. and Khushi, M. (2020). Ga-mssr: Genetic algorithm maximizing sharpe and
sterlingratiomethodforrobotrading.