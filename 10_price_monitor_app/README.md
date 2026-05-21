# Price Monitor - Мониторинг цен на маркетплейсах

Мобильное приложение для отслеживания цен и скидок на товары с маркетплейсов Wildberries и Ozon. Получайте уведомления о снижении цен, анализируйте историю изменений и находите лучшие предложения.

## Описание проекта

Price Monitor - это мобильный клиент для мониторинга цен на маркетплейсах Wildberries и Ozon.

Основные возможности:
- Лента лучших скидок с бесконечной прокруткой
- Графики истории цен за 30 дней
- Персональные алерты на снижение цены
- Категории товаров (электроника, одежда, дом, дети, красота, спорт, авто, питомцы)
- Избранные товары с локальным хранением
- Профиль пользователя с подпиской VIP
- Темная и светлая тема оформления
- Push-уведомления через Firebase Cloud Messaging
- Переход к покупке через партнерские ссылки (WebView)

## Технологии

- **React Native** 0.73.6 (bare workflow, Android only)
- **TypeScript** - строгая типизация
- **React Navigation** - навигация (bottom tabs + native stack)
- **React Query** (@tanstack/react-query) - управление состоянием запросов
- **Firebase Cloud Messaging** - push-уведомления
- **react-native-chart-kit** + react-native-svg - графики цен
- **react-native-webview** - просмотр страниц товаров
- **AsyncStorage** - локальное хранение данных
- **react-native-vector-icons** - иконки Material Community Icons
- **react-native-splash-screen** - экран загрузки

## Структура проекта

```
10_price_monitor_app/
├── App.tsx                    # Корневой компонент приложения
├── index.js                   # Точка входа React Native
├── package.json               # Зависимости и скрипты
├── tsconfig.json              # Конфигурация TypeScript
├── babel.config.js            # Конфигурация Babel
├── metro.config.js            # Конфигурация Metro bundler
├── android/                   # Android-проект (Gradle)
│   ├── build.gradle           # Project-level Gradle config
│   ├── settings.gradle        # Gradle settings
│   ├── gradle.properties      # Gradle properties
│   └── app/
│       ├── build.gradle       # App-level Gradle config
│       └── src/main/
│           └── AndroidManifest.xml
└── src/
    ├── api/
    │   ├── mockData.ts        # Мок-данные (20+ товаров)
    │   └── services.ts        # API-сервисы (имитация запросов)
    ├── components/
    │   ├── AlertItem.tsx       # Элемент списка алертов
    │   ├── CategoryCard.tsx    # Карточка категории
    │   ├── DiscountBadge.tsx   # Бейдж скидки
    │   ├── EmptyState.tsx     # Пустое состояние
    │   ├── PriceChart.tsx     # Полный график цен (30 дней)
    │   ├── ProductCard.tsx    # Карточка товара
    │   └── SparklineChart.tsx # Мини-график тренда (7 дней)
    ├── hooks/
    │   ├── useFavorites.ts    # Хук для избранного (AsyncStorage)
    │   └── useTheme.ts        # Хук для темы
    ├── navigation/
    │   └── AppNavigator.tsx   # Навигация (tabs + stack)
    ├── screens/
    │   ├── AlertsScreen.tsx       # Экран алертов
    │   ├── CategoriesScreen.tsx   # Экран категорий
    │   ├── FavoritesScreen.tsx    # Экран избранного
    │   ├── FeedScreen.tsx         # Главная лента скидок
    │   ├── ProductDetailScreen.tsx # Детали товара
    │   ├── ProfileScreen.tsx      # Профиль пользователя
    │   └── SettingsScreen.tsx     # Настройки
    ├── theme/
    │   ├── colors.ts          # Цветовые схемы (light/dark)
    │   └── ThemeContext.tsx   # React Context для темы
    ├── types/
    │   └── index.ts           # TypeScript интерфейсы
    └── utils/
        └── formatPrice.ts     # Форматирование цен (рубли)
```

## Начало работы

### Предварительные требования

- **Node.js** 18+ (рекомендуется LTS)
- **JDK** 17+ (Java Development Kit)
- **Android SDK** 34 (через Android Studio или sdkmanager)
- **React Native CLI** (`npx react-native`)
- **Android Studio** (для эмулятора и SDK менеджера)

### Установка

```bash
# Клонировать репозиторий
git clone <repository-url>
cd 10_price_monitor_app

# Установить зависимости
npm install
```

## Запуск

### Разработка

```bash
# Запуск на подключенном устройстве или эмуляторе
npx react-native run-android

# Или запустить Metro bundler отдельно
npx react-native start
```

### Подключение устройства

1. **Эмулятор**: откройте Android Studio > Device Manager > создайте или запустите AVD (API 34)
2. **Физическое устройство**:
   - Включите "Режим разработчика" в настройках телефона
   - Включите "Отладка по USB"
   - Подключите кабелем и подтвердите доступ на устройстве
   - Проверьте подключение: `adb devices`

## Сборка Release APK

```bash
cd android
./gradlew assembleRelease
```

Готовый APK будет находиться в:
```
android/app/build/outputs/apk/release/app-release.apk
```

## Сборка AAB для Google Play

```bash
cd android
./gradlew bundleRelease
```

Готовый AAB будет находиться в:
```
android/app/build/outputs/bundle/release/app-release.aab
```

## Подпись приложения

### 1. Генерация keystore

```bash
keytool -genkeypair -v -storetype PKCS12 -keystore price-monitor.keystore -alias price-monitor -keyalg RSA -keysize 2048 -validity 10000
```

Сохраните файл `price-monitor.keystore` в надежном месте. **Никогда не добавляйте его в Git!**

### 2. Создание файла keystore.properties

Создайте файл `android/keystore.properties`:

```properties
storeFile=../price-monitor.keystore
storePassword=ваш_пароль
keyAlias=price-monitor
keyPassword=ваш_пароль_ключа
```

Добавьте `keystore.properties` в `.gitignore`.

### 3. Настройка подписи в build.gradle

Добавьте в `android/app/build.gradle`:

```groovy
def keystorePropertiesFile = rootProject.file("keystore.properties")
def keystoreProperties = new Properties()
if (keystorePropertiesFile.exists()) {
    keystoreProperties.load(new FileInputStream(keystorePropertiesFile))
}

android {
    ...
    signingConfigs {
        release {
            storeFile file(keystoreProperties['storeFile'] ?: 'debug.keystore')
            storePassword keystoreProperties['storePassword'] ?: ''
            keyAlias keystoreProperties['keyAlias'] ?: ''
            keyPassword keystoreProperties['keyPassword'] ?: ''
        }
    }
    buildTypes {
        release {
            signingConfig signingConfigs.release
            minifyEnabled true
            proguardFiles getDefaultProguardFile('proguard-android-optimize.txt'), 'proguard-rules.pro'
        }
    }
}
```

## Публикация в Google Play

1. **Создайте аккаунт разработчика** на [Google Play Console](https://play.google.com/console) (единоразовая оплата $25)
2. **Создайте приложение** в консоли
3. **Загрузите AAB файл** (`app-release.aab`) в раздел "Production" или "Internal testing"
4. **Заполните информацию о приложении**:
   - Название, описание, скриншоты (см. [STORE_LISTING.md](./STORE_LISTING.md))
   - Иконка 512x512 px
   - Feature graphic 1024x500 px
5. **Настройте рейтинг контента** - пройдите опросник (результат: 0+ / Everyone)
6. **Ценообразование** - выберите "Бесплатно"
7. **Политика конфиденциальности** - укажите URL (см. [PRIVACY_POLICY.md](./PRIVACY_POLICY.md))
8. **Отправьте на проверку** - обычно рассмотрение занимает 1-7 дней

## Публикация в RuStore

1. **Создайте аккаунт разработчика** на [RuStore Console](https://console.rustore.ru)
2. **Создайте приложение** в личном кабинете
3. **Загрузите APK** (RuStore принимает APK, не только AAB):
   ```bash
   cd android && ./gradlew assembleRelease
   ```
4. **Заполните информацию** о приложении:
   - Название, описание, скриншоты (см. [STORE_LISTING.md](./STORE_LISTING.md))
   - Иконка приложения
5. **Укажите URL политики конфиденциальности** (обязательное требование RuStore)
6. **Категория**: Покупки
7. **Возрастной рейтинг**: 0+
8. **Отправьте на модерацию** - обычно рассмотрение занимает 1-3 рабочих дня

> **Примечание**: RuStore не требует оплаты за аккаунт разработчика.

## Firebase настройка

### 1. Создание проекта

1. Перейдите в [Firebase Console](https://console.firebase.google.com)
2. Создайте новый проект (или выберите существующий)
3. Добавьте Android-приложение с package name: `com.pricemonitor.app`

### 2. Скачивание google-services.json

1. В настройках проекта Firebase скачайте файл `google-services.json`
2. Поместите его в `android/app/google-services.json`

### 3. Настройка FCM (Push-уведомления)

Убедитесь, что в `android/app/build.gradle` подключен плагин:

```groovy
apply plugin: 'com.google.gms.google-services'
```

В `android/build.gradle` (project-level) добавлен classpath:

```groovy
classpath 'com.google.gms:google-services:4.4.0'
```

Приложение использует `@react-native-firebase/messaging` для:
- Получения push-токена устройства
- Обработки фоновых уведомлений
- Показа уведомлений о скидках и алертах

### 4. Тестирование уведомлений

1. Получите FCM-токен через `messaging().getToken()`
2. Отправьте тестовое уведомление через Firebase Console > Cloud Messaging
3. Или используйте Firebase Admin SDK на сервере

## Иконка приложения

### Подготовка иконки

1. Подготовьте иконку размером **512x512 px** (для магазинов) и **1024x1024 px** (исходник)
2. Формат: PNG с прозрачным фоном (для adaptive icon) или без прозрачности

### Размещение по плотностям экрана

Разместите иконки в соответствующих директориях:

```
android/app/src/main/res/
├── mipmap-mdpi/       (48x48 px)
├── mipmap-hdpi/       (72x72 px)
├── mipmap-xhdpi/      (96x96 px)
├── mipmap-xxhdpi/     (144x144 px)
└── mipmap-xxxhdpi/    (192x192 px)
```

### Использование Android Studio Image Asset

1. Откройте проект в Android Studio
2. Правый клик на `android/app/src/main/res` > New > Image Asset
3. Выберите исходное изображение
4. Настройте padding и background для Adaptive Icon
5. Нажмите "Next" > "Finish"

## Splash Screen

Приложение использует `react-native-splash-screen` для отображения экрана загрузки.

### Настройка

1. Файл splash-экрана: `android/app/src/main/res/layout/launch_screen.xml`
2. Фоновое изображение: `android/app/src/main/res/drawable/splash.png`
3. Цвет фона настраивается в `android/app/src/main/res/values/colors.xml`

### Кастомизация

- Замените `splash.png` на свое изображение (рекомендуется логотип на фирменном фоне)
- В `MainActivity.java` вызывается `SplashScreen.show(this)` в `onCreate`
- В `App.tsx` вызывается `SplashScreen.hide()` после загрузки данных

## Лицензия

MIT License

Copyright (c) 2024 Price Monitor

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
