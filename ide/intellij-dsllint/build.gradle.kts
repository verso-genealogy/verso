import org.jetbrains.intellij.platform.gradle.IntelliJPlatformType
import org.jetbrains.intellij.platform.gradle.TestFrameworkType

plugins {
    id("org.jetbrains.intellij.platform") version "2.20.1"
    kotlin("jvm") version "2.4.21"
}

group = providers.gradleProperty("pluginGroup").get()
version = providers.gradleProperty("pluginVersion").get()

repositories {
    mavenCentral()
    intellijPlatform {
        defaultRepositories()
    }
}

dependencies {
    intellijPlatform {
        pycharm(providers.gradleProperty("platformVersion"))
        bundledPlugin("PythonCore")
        testFramework(TestFrameworkType.Platform)
    }
    testImplementation(kotlin("test"))
}

intellijPlatform {
    pluginConfiguration {
        version = providers.gradleProperty("pluginVersion")
        ideaVersion {
            sinceBuild = providers.gradleProperty("pluginSinceBuild")
            untilBuild = provider { null }
        }
    }
    pluginVerification {
        ides {
            providers.gradleProperty("pluginVerifyVersions").get().split(',').forEach {
                create(IntelliJPlatformType.PyCharm, it.trim())
            }
            // An installed IDE, e.g. -PverifyLocalIde=$HOME/Applications/GoLand.app
            providers.gradleProperty("verifyLocalIde").orNull?.let { local(it) }
        }
    }
}

kotlin {
    jvmToolchain(21)
}
