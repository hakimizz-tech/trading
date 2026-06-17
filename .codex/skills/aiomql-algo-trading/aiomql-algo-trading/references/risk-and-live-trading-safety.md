# Risk and Live Trading Safety

## Non-negotiable rules

- Generated code must not hardcode broker credentials.
- Generated code must not default to live trading.
- Generated code must not claim profitability.
- Generated code must not hide risk controls behind vague comments.
- Generated code must make live trading opt-in through an explicit parameter or config value.

## Live trading confirmation checklist

Before producing or running code that can place live orders, confirm:

1. The user explicitly asked for live execution.
2. The user identified the account as demo or live.
3. The user supplied or approved risk per trade.
4. The strategy has a stop-loss rule.
5. The strategy has a max open positions rule.
6. The strategy has a max daily loss or emergency shutdown rule.
7. The strategy has a spread or slippage guard where applicable.
8. The user understands that losses are possible.

## Risk controls to include in code

At minimum, consider:

- Max risk per trade.
- Max lot size.
- Min and max stop-loss distance.
- Max spread.
- Max open positions per symbol.
- Max total open positions.
- Max daily loss.
- Cooldown after loss.
- Session windows.
- News filter placeholder if requested.
- Dry-run mode.

## Secrets handling

Create this file only:

```json
{
  "login": 12345678,
  "password": "replace_me_locally",
  "server": "YourBroker-Demo"
}
```

Name it `aiomql.json.example`. Add the real `aiomql.json` to `.gitignore`.

Recommended `.gitignore` additions:

```gitignore
aiomql.json
*.db
*.sqlite
logs/
trade_results/
.env
```

## Review questions for the user

Ask these when requirements are missing:

- Which symbols should the bot trade?
- Which timeframe should generate entries?
- What session hours should be active?
- Demo or live?
- What risk percentage or fixed lot should be used?
- What stop-loss and take-profit method should be used?
- Should the bot manage existing positions or only new entries?
- How should results be stored?

## Red flags

Pause and clarify if the user requests:

- No stop-loss live trading.
- Unlimited position scaling.
- Guaranteed profits.
- Credentials embedded in code.
- Ignoring broker errors.
- Trading all symbols without filters.
- Running live on an untested strategy.
