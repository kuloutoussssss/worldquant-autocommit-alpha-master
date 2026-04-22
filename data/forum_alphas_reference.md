# WorldQuant BRAIN Alpha 参考表达式集
> 来源：论坛帖子收集，共 48 个表达式
> 整理时间：2026-04-18

---

## 1. 回归中性化系列

### 1.1 regression_neut + IR
```
IR = abs(ts_mean(returns,252)/ts_std_dev(returns,252));
regression_neut(vector_neut(ts_zscore(vec_max(ANALYST)/close, 126),ts_median(cap, 126)),IR)
```

### 1.2 regression_neut 双层嵌套
```
regression_neut(regression_neut(a2,b1),IR)
a = ts_zscore({datafield}, 252)
a1 = group_neutralize(a, bucket(rank(cap), range='0.1,1,0.1'))
a2 = group_neutralize(a1, industry)
b = ts_zscore(cap, 252)
b1 = group_neutralize(b, industry)
c = regression_neut(a2,b1)
```

### 1.3 regression_neut + ts_regression
```
regression_neut(regression_neut(modified,short_term_excess_return),long_term_excess_return)
market_pv = group_mean(adv20,1,market);
modified = vec_avg(anl);
short_term_excess_return = ts_mean(pv-market_pv,5);
long_term_excess_return = ts_delay(ts_mean(pv-market_pv,120),120);
```

---

## 2. 情绪/恐惧因子系列

### 2.1 恐惧因子
```
market_return = group_mean(returns,1,market);
fear = ts_mean(abs(returns - market_return)/(abs(returns)+abs(market_return)),20);
vhat = ts_regression(volume,ts_mean(vec_avg({Sentiment}),5),120);
ehat = ts_regression(returns-market_return,vhat,120);
alpha = group_neutralize(-ehat*rank(fear),bucket(rank(cap),range='0,1,0.1'));
trade_when(abs(returns)<0.075,regression_neut(alpha,volume),abs(returns)>0.1)
```
> Decay=20, Neutralize=industry

### 2.2 新闻情绪 + IR
```
nss = ts_backfill(se_score,20);
processed_news_sentiment = (nss - ts_mean(nss,250))/ts_std_dev(nss,250);
monthly_returns = ts_ir(returns,20);
processed_returns = ts_backfill(monthly_returns, 20);
ranked_sentiment = ts_mean(group_rank(processed_news_sentiment,industry), 20);
ranked_returns = ts_mean(group_rank(-processed_returns,industry), 20);
alpha = subtract(ranked_sentiment, ranked_returns);
```

### 2.3 条件情绪过滤
```
group_rank(
 filter(
  sigmoid(
   if_else(
    greater(ts_zscore(news_sentiment, 30), 1),
    ts_zscore(news_sentiment, 30),
    0
   )
  ),
  h="1 2 3 4",
  t="0.5"
 ),
 industry
)
```

---

## 3. 波动率/方差系列

### 3.1 条件波动率
```
d1_level=ts_max(vec_stddev({data}),20);
d1_stability=ts_kurtosis(vec_stddev({data}),20);
mkt_level=group_min(d1_stability,industry);
-group_neutralize(d1_stability<=mkt_level?-d1_level:d1_level,bucket(rank(cap),range="0.1,1,0.1"))
```

### 3.2 换手率 + 波动率组合
```
Turn20_ = ts_mean(volume/sharesout, 20);
Turn20 = group_neutralize(Turn20_, bucket(rank(cap), range="0.1,1,0.1"));
STR_ = ts_std_dev(volume/sharesout, 20);
STR = group_neutralize(STR_, bucket(rank(cap), range="0.1,1,0.1"));
score2 = rank(- nan_mask(Turn20, if_else(rank(STR) < 0.5, 1, -1))) * 0.5;
score3 = rank(nan_mask(Turn20, if_else(rank(STR) >= 0.5, 1, -1))) * 0.5;
signal_ = add(rank(STR), score2, score3, filter = true);
signal = left_tail(rank(signal_), maximum=0.98);
- group_rank(signal, bucket(rank(cap), range="0.1,1,0.1"))
```

### 3.3 夜盘隔夜收益
```
overnight_ret = (open - ts_delay(close,1))/ts_delay(close,1);
abs_ovn_ret = abs (overnight_ret);
turn = volume/sharesout;
turn_d1 = ts_delay(turn, 1);
corr = ts_corr (abs_ovn_ret, turn_d1,7);
-(corr)
```

---

## 4. 资金流向/订单流系列

### 4.1 大单净流出
```
small_sell = vec_sum(SPECIAL SELL ORDER);
small_buy = vec_sum(SPECIAL BUY ORDER);
fac = - small_sell - small_buy;
fac_diff_mean = power(rank(fac - group_mean(fac, 1, subindustry)),D);
IR = abs(ts_mean(returns,126)/ts_std_dev(returns,126));
group_neutralize(regression_neut(group_neutralize(fac_diff_mean,bucket(rank(cap), range='-0.1,1,0.1')),IR),sta1_top3000c10)
```

### 4.2 大小单分离
```
small_sell = vec_avg(pv27_sell_value_small_order);
small_buy = vec_avg(pv27_buy_value_small_order);
large_sell = vec_avg(pv27_sell_value_exlarge_order);
large_buy = vec_avg(pv27_buy_value_exlarge_order);
fac_small = small_sell + small_buy;
fac_large = large_sell + large_buy;
fac_small_diff_mean = fac_small - group_mean(fac_small, 1, subindustry);
fac_large_diff_mean = fac_large - group_mean(fac_large, 1, subindustry);
factor = if_else(rank(cap)<0.05, fac_small_diff_mean, fac_large_diff_mean);
if_else(rank(factor) <0.45, rank(factor)*0.55, factor, -1)
```

---

## 5. 财报/基本面回归系列

### 5.1 财务变量回归（5种系列）
```
# 系列1
A = sign(finance_var)*log(abs(finance_var)+1);
B = sign(finance_var)*log(abs(finance_var)+1);
regression_neut(A,B)

# 系列2
ts_regression(ts_zscore(A,500), ts_zscore(B,500),500)

# 系列3
1/ts_std_dev(ts_regression(ts_zscore(A,500), ts_zscore(B,500),500)，500)

# 系列4
residual = ts_regression(ts_zscore(A,500), ts_zscore(B,500),500);
residual/ts_std_dev(residual，500)

# 系列5
ts_regression(ts_zscore(A,500), timestep(500),500)
```

### 5.2 多财务因子综合评分
```
roa = group_zscore(fnd72_s_pit_or_cf_q_cf_net_inc*2/(assets+last_diff_value(assets,300)),sector);
pb = group_zscore(mdl175_bp,sector);
ITR = group_zscore(inventory_turnover,sector);
DtA = group_zscore(mdl175_debtsassetratio,sector);
WAtA = group_zscore(mdl175_workingcapital/assets,sector);
NAYOY = group_zscore(mdl175_netassetgrowrate,sector);
int2A = group_zscore(mdl175_intangibleassetratio,sector);
rank(regression_neut(regression_neut(regression_neut(regression_neut(regression_neut(regression_neut(regression_neut(roa,pb),ITR),DtA),WAtA),NAYOY),int2A),log(cap)))
```

### 5.3 分析师综合因子
```
tmp = (group_rank(fnd72_s_pit_or_cf_q_cf_cash_from_inv_act, sector) > 0.5) * 4
    + (group_rank(fnd72_s_pit_or_cf_q_cf_cash_from_fnc_act, sector) > 0.5) * 2
    + (group_rank(fnd72_s_pit_or_cf_q_cash_from_oper, sector) > 0.5) * 1;
2 * (tmp == 1) - (tmp == 2) - (tmp == 6)
```

---

## 6. 反转因子系列

### 6.1 短期delta反转
```
a = -ts_delta(datafield,3);
b = abs(ts_mean(returns,252)/ts_std_dev(returns,252));
group_neutralize(vector_neut(a,b),subindustry)
```

### 6.2 "小而稳"因子
```
a = - A * ts_std_dev(A, 20);
b = abs(ts_mean(returns,252)/ts_std_dev(returns,252));
vector_neut(a,b)
```

### 6.3 方差差异
```
power(ts_std_dev(abs(returns),30),2) - power(ts_std_dev(returns,30),2)
IR = abs(ts_mean(returns,252)/ts_std_dev(returns,252));
r = returns;
a = power(ts_std_dev(abs(r)+r,30),2);
b = power(ts_std_dev((abs(r)-r),30),2);
c = regression_neut(b-a,IR);
group_neutralize(group_neutralize(c,bucket(rank(cap),range='0.2,1,0.2')),country)
```

---

## 7. 趋势/动量系列

### 7.1 行业趋势
```
industry_open = group_mean(open, cap, subindustry);
industry_close = group_mean(close, cap, subindustry);
industry_high = group_mean(high, cap, subindustry);
industry_low = group_mean(low, cap, subindustry);
Trends = if_else(industry_close > ts_delay(industry_close, 40),
    industry_close/ts_max(industry_high, 100),
    rank(industry_close/ts_min(industry_low, 500))-1);
OTSM = ts_sum((industry_high-ts_delay(industry_close, 1))/(ts_delay(industry_close, 1)-industry_low+1), 90);
DTSM = ts_sum((industry_high-industry_open)/(industry_open-industry_low+1), 5);
TSM = rank(OTSM) + rank(DTSM);
rank(Trends) + rank(TSM)
```

### 7.2 复合趋势
```
my_group = bucket(rank(cap), range="0,1,0.1");
alpha=rank(group_rank(ts_decay_linear(volume/ts_sum(volume,252),10),my_group)
    *group_rank(ts_rank(vec_avg({Fundamental}),180),my_group)
    *group_rank(-ts_delta(close,5),my_group));
trade_when(volume>adv20,group_neutralize(alpha,my_group2),-1)
```

---

## 8. 综合交易信号系列

### 8.1 布林带交易
```
triggerTradeexp = (ts_arg_min(volume, 5) > 3) || (volume >= ts_sum(volume, 5) / 5);
alphaexp = rank(rank((high + low) / 2 - close) * rank((mdl175_roediluted*mdl175_cashrateofsales)));
tradeExitexp = -1;
trade_when(triggerTradeexp, alphaexp, tradeExitexp)
```

### 8.2 多条件过滤
```
turnover_rank = ts_mean(rank(volume / (sharesout * 1000000)), 22);
spe = rank(vec_avg(anl17_d1_spe_tse));
bp = rank(vec_avg(anl17_d1_bp_tse));
alpha = spe - bp;
turnover_rank > 0.1 ? alpha : 0
```

### 8.3 条件入场
```
trade_when(ts_rank(ts_std_dev(returns,10),252)<0.9,-regression_neut(...),-1)
trade_when(volume>adv20,alpha,-1)
```

---

## 9. 风险/分组中性化系列

### 9.1 三层中性化
```
regression_neut(
    group_neutralize(
        group_zscore({data},sector),
        bucket(rank(cap),range="0.1,1,0.1")
    ),
    group_neutralize(
        group_zscore(cap,sector),
        bucket(rank(cap),range="0.1,1,0.1")
    ),
    ts_ir(returns-group_median(returns,sector),126)
)
```

### 9.2 风险评分
```
risk = rank(-ts_av_diff(vec_min({Analyst Std}),360));
alpha = rank((1-risk)*group_rank(ts_scale(vec_max({OptionHighPrice})/close,120),industry));
group_neutralize(ts_mean(alpha,2),group)
```
> Decay=10, Neutralize=industry

---

## 10. 通用公式模板

### 10.1 模板1
```
{ts_opr_1}({group_opr}(ts_opr_2(rank({vector_opr}({pv_field})),rank({vector_opr}({vol_field})),{days1}),{grouping}){,days2})
```

### 10.2 模板2
```
<Arithmetich_or Transformational_op>(
    <ts_compare_op>(<Company Fundamental Data for Equity>, <Price Volume Data for Equity>, <days>)
    *<Company Fundamental Data for Equity>
)
```

### 10.3 模板3（CHINA市场）
```
turn = volume/sharesout;
turn20 = rank(regression_neut(-ts_mean(turn,20),densify(cap)));
STR = regression_neut(-ts_std_dev(turn,20),densify(cap));
UTR = STR + turn20 * (STR/(1+abs(STR)));
regression_neut(regression_neut(regression_neut(sign(UTR)*power(abs(UTR),0.5),turn20),vwap),ts_delta(retained_earnings/sharesout,120))
```

---

## 📌 关键技巧总结

| 技巧 | 公式 | 说明 |
|------|------|------|
| **IR中性化** | `regression_neut(factor, IR)` | 残差因子用IR做回归 |
| **分组中性化** | `group_neutralize(x, bucket(rank(cap)))` | 分档市值中性 |
| **多层嵌套** | `regression_neut(group_neutralize(...))` | 逐步剥离风险 |
| **ts_backfill** | `ts_backfill(data, 20)` | 财务数据时序填充 |
| **小而稳** | `A * ts_std_dev(A, 20)` | 波动率加权 |
| **短期反转** | `-ts_delta(A, 3)` | 3天delta反转 |
| **资金流** | `small_sell - small_buy` | 订单流净流入 |
| **恐惧因子** | `abs(returns - mkt_return) / (|returns| + |mkt_return|)` | 偏离度 |
| **ts_ir** | `ts_mean(x,252) / ts_std_dev(x,252)` | 信息比率 |

---

## ⚙️ 常用参数设置

| 参数 | 常用值 |
|------|--------|
| Decay | 10, 20, 30, 60, 120 |
| Neutralize | industry, sector, subindustry, bucket(rank(cap)) |
| Universe | TOP3000, TOP500 |
| Truncation | 0.02 ~ 0.08 |
