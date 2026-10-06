# cWGAN-GP augmentation

| class | real | added | filter acceptance | real-vs-fake AUC (kept) |
|---|---|---|---|---|
| DoS Slowloris | 3992 | 343 | 8.5% | 1.0 |
| DoS Slowhttptest | 3576 | 324 | 5.7% | 1.0 |
| FTP-Patator | 2789 | 2211 | 98.5% | 1.0 |
| SSH-Patator | 2092 | 2908 | 86.1% | 1.0 |
| Web Attack | 1439 | 3423 | 24.0% | 1.0 |
| Botnet | 1343 | 3657 | 51.4% | 1.0 |

AUC 0.5 = synthetic indistinguishable from real; 1.0 = trivially fake.