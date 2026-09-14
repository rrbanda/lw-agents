# pom.xml Editing Patterns

## Property-controlled version
```xml
<properties>
  <jackson.version>2.13.2</jackson.version>
</properties>
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>com.fasterxml.jackson.core</groupId>
      <artifactId>jackson-databind</artifactId>
      <version>${jackson.version}</version>
    </dependency>
  </dependencies>
</dependencyManagement>
```
Edit the `<jackson.version>` property value. Do NOT edit the `<version>` tag.

## BOM-managed version
```xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>com.fasterxml.jackson</groupId>
      <artifactId>jackson-bom</artifactId>
      <version>2.13.2</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>
```
Edit the BOM version to update ALL Jackson modules at once.

## Direct inline version
```xml
<dependencies>
  <dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
    <version>2.13.2</version>
  </dependency>
</dependencies>
```
Edit the `<version>` tag directly.

## Multi-module projects
Check the parent pom.xml first. Most managed versions live there.
Module pom.xml files usually inherit and don't repeat the version.
