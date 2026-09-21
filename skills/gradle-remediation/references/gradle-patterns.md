# Gradle Dependency Version Patterns

## Direct declaration

```groovy
// build.gradle
dependencies {
    implementation 'com.fasterxml.jackson.core:jackson-databind:2.13.2'
}
```

Fix: change version inline.

## ext/extra property

```groovy
// build.gradle
ext {
    jacksonVersion = '2.13.2'
}
dependencies {
    implementation "com.fasterxml.jackson.core:jackson-databind:${jacksonVersion}"
}
```

Fix: change the property value.

## Kotlin DSL

```kotlin
// build.gradle.kts
val jacksonVersion = "2.13.2"
dependencies {
    implementation("com.fasterxml.jackson.core:jackson-databind:$jacksonVersion")
}
```

Fix: change the val declaration.

## Version catalog (libs.versions.toml)

```toml
# gradle/libs.versions.toml
[versions]
jackson = "2.13.2"

[libraries]
jackson-databind = { module = "com.fasterxml.jackson.core:jackson-databind", version.ref = "jackson" }
```

Fix: change version in `[versions]` section.

## BOM / Platform dependency

```groovy
dependencies {
    implementation platform('com.fasterxml.jackson:jackson-bom:2.13.2')
    implementation 'com.fasterxml.jackson.core:jackson-databind'
}
```

Fix: change the BOM version. Individual library versions inherit from it.

## Forced resolution strategy

```groovy
// When a transitive dependency pins an old version
configurations.all {
    resolutionStrategy {
        force 'io.netty:netty-codec-http:4.1.108.Final'
    }
}
```

Use when: the dependency is transitive and no direct declaration exists.

## buildSrc pattern

```kotlin
// buildSrc/src/main/kotlin/Versions.kt
object Versions {
    const val jackson = "2.13.2"
}
```

Fix: change the constant in `buildSrc`.

## gradle.properties

```properties
# gradle.properties
jacksonVersion=2.13.2
```

```groovy
// build.gradle
dependencies {
    implementation "com.fasterxml.jackson.core:jackson-databind:${jacksonVersion}"
}
```

Fix: change the property in `gradle.properties`.

## Wrapper detection

Always use `./gradlew` when available (checked by `os.path.isfile("gradlew")`).
Fall back to system `gradle` only when no wrapper exists.
