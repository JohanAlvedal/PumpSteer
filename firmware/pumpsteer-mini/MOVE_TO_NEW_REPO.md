# Moving PumpSteer Mini to the standalone repository

The temporary development copy currently lives at:

`JohanAlvedal/PumpSteer` → branch `mini-development` → `firmware/pumpsteer-mini/`

The target repository is:

`JohanAlvedal/PumpSteer-Mini`

## Safe migration procedure

1. Copy the complete contents of `firmware/pumpsteer-mini/` to the root of `PumpSteer-Mini`.
2. Keep directory names and hidden files, including `.github/` and `.gitignore`.
3. Verify that `CMakeLists.txt`, `sdkconfig.defaults`, `components/`, `main/` and `host_tests/` are present at repository root.
4. Run host tests.
5. Build the ESP-IDF firmware for `esp32s3`.
6. Push the standalone repository.
7. Verify GitHub Actions in the new repository.
8. Only after the standalone repository is confirmed complete should the temporary copy be considered for removal from the original PumpSteer repository.

## Host test verification

```bash
cd host_tests
cmake -S . -B build
cmake --build build
ctest --test-dir build --output-on-failure
```

## ESP-IDF verification

```bash
idf.py set-target esp32s3
idf.py build
```

## Do not do during migration

- Do not delete the source copy first.
- Do not manually flatten the `components/` directory.
- Do not copy build output or generated `sdkconfig` files.
- Do not add Wi-Fi passwords, MQTT passwords or other credentials to Git.
- Do not merge Mini into the Home Assistant custom component.

The standalone repository should retain the same architectural rule: PumpSteer Mini is an independent controller and Home Assistant is optional.
