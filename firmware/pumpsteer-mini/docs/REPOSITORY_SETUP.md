# Repository setup after migration

After moving the project to `JohanAlvedal/PumpSteer-Mini`:

1. Confirm `main` is the default branch.
2. Enable branch protection when the first stable CI workflow is green.
3. Enable Issues.
4. Keep Actions enabled for host tests.
5. Add repository topics such as `esp32`, `esp-idf`, `heat-pump`, `home-assistant`, `mqtt`, `bthome`, and `shelly` when appropriate.
6. Decide and add a software license before the first public release.
7. Add release artifacts only after OTA/partition strategy is finalized.

Do not enable automated dependency changes that can silently alter ESP-IDF behavior without review.
