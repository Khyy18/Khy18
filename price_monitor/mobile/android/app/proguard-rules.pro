# React Native
-keep class com.facebook.react.** { *; }
-keep class com.facebook.hermes.** { *; }
-keep class com.facebook.jni.** { *; }
-dontwarn com.facebook.react.**

# Hermes
-keep class com.facebook.hermes.unicode.** { *; }
-keep class com.facebook.jni.** { *; }

# react-native-webview
-keepclassmembers class * {
    @android.webkit.JavascriptInterface <methods>;
}
-keepattributes JavascriptInterface

# Firebase
-keep class com.google.firebase.** { *; }
-dontwarn com.google.firebase.**

# react-native-vector-icons
-keep class com.oblador.vectoricons.** { *; }

# react-native-svg
-keep public class com.horcrux.svg.** { *; }

# Keep native methods
-keepclassmembers class * {
    native <methods>;
}

# Annotations
-keepattributes *Annotation*
-keepattributes Signature
-keepattributes Exceptions
