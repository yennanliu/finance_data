# claude_financial_services

- Finance report with claude code official plugins
	- https://github.com/anthropics/financial-services-plugins

## Cmd

> **Note:** Use the full qualified skill name (e.g., `/financial-analysis:dcf-model META`)

| Slash Command                       | Parameters        | Description                              |
|-------------------------------------|-------------------|------------------------------------------|
| /financial-analysis:comps-analysis  | [company]         | Comparable company analysis              |
| /financial-analysis:dcf-model       | [company]         | DCF valuation model                      |
| /financial-analysis:dcf             | [company]         | DCF with comps-informed terminal value   |
| /equity-research:earnings-analysis  | [company] [quarter] | Post-earnings update report            |
| /investment-banking:strip-profile   | [company]         | One-page company profile                 |
| /private-equity:ic-memo             | [project name]    | Investment committee memo                |
| /private-equity:source              | [criteria]        | Deal sourcing                            |
| /wealth-management:client-review    | [client]          | Client meeting prep                      |