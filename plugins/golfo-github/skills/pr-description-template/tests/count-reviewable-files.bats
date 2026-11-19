#!/usr/bin/env bats

# count-reviewable-files.sh reads the changed paths from stdin, so each test pipes a path list
# and checks the count a reviewer would expect for the PR body marker.

setup() {
  COUNT_SCRIPT="${BATS_TEST_DIRNAME}/../scripts/count-reviewable-files.sh"
}

count_paths() {
  printf '%s\n' "$@" | bash "$COUNT_SCRIPT"
}

@test "counts JavaScript and TypeScript product code and skips tests, mocks, assets and styles" {
  run count_paths src/App.tsx src/utils/date.ts src/App.test.tsx tests/helpers.ts __mocks__/client.ts assets/logo.svg styles/theme.scss
  [ "$status" -eq 0 ]
  [ "$output" = "2" ]
}

@test "counts Kotlin and Java sources and skips their tests, integration tests and Gradle scripts" {
  run count_paths \
    app/src/main/kotlin/com/acme/UserService.kt \
    app/src/main/java/com/acme/UserRepository.java \
    app/src/main/java/com/acme/Audit.java \
    app/src/test/kotlin/com/acme/UserServiceTest.kt \
    app/src/main/java/com/acme/UserRepositoryIT.java \
    app/src/androidTest/java/com/acme/LoginScreenTest.java \
    app/src/main/kotlin/com/acme/FakeClock.kt \
    build.gradle.kts \
    app/build.gradle \
    settings.gradle.kts
  [ "$status" -eq 0 ]
  [ "$output" = "3" ]
}

@test "counts Go sources and skips _test.go, testdata, vendor and generated protobuf code" {
  run count_paths cmd/server/main.go internal/user/service.go internal/user/service_test.go internal/user/testdata/input.go vendor/github.com/acme/lib/lib.go api/user.pb.go
  [ "$status" -eq 0 ]
  [ "$output" = "2" ]
}

@test "counts Python, Ruby, Swift, Rust, C#, shell and SQL sources and skips their test conventions" {
  run count_paths \
    src/app.py tests/test_app.py src/test_utils.py conftest.py \
    lib/user.rb spec/user_spec.rb \
    Sources/App/View.swift Tests/AppTests/ViewTests.swift \
    src/bin/cli.rs \
    src/Billing/Invoice.cs src/Billing/InvoiceTests.cs \
    scripts/deploy.sh db/migrations/001_users.sql
  [ "$status" -eq 0 ]
  [ "$output" = "7" ]
}

@test "keeps names that only look like tests, such as Latest, Contest or Testimonial" {
  run count_paths src/Latest.kt src/Contest.java src/Testimonial.kt src/latest.go src/TestUtils.kt
  [ "$status" -eq 0 ]
  [ "$output" = "4" ]
}

@test "skips dot directories, root config, tooling configuration, declarations and documentation" {
  run count_paths .github/scripts/release.js .eslintrc.js config/default.js jest.config.js eslint-import-core-modules.js src/types.d.ts README.md docs/setup.md app/translations/en/messages.json
  [ "$status" -eq 0 ]
  [ "$output" = "0" ]
}

@test "accepts Windows line endings in the path list" {
  run bash -c "printf 'src/main.go\r\nsrc/main_test.go\r\n' | bash '$COUNT_SCRIPT'"
  [ "$status" -eq 0 ]
  [ "$output" = "1" ]
}
