# Choosing when intros play

A schedule says which collection plays, and when. For example: "Halloween intros play every year from October 1 to October 31."

## Making a schedule

On [When They Play](app:/schedules), press **New schedule**, give it a name, and answer three questions.

**1. What plays.** Pick a collection, then choose:

- **Pick one at random each time:** a different intro before each movie.
- **Play them all, one after another:** every video in the collection, in order.

**2. When.**

- **Every year, between two dates:** for seasons, like all of October. It repeats every year.
- **Between two dates, once:** for a one-off, like a movie night or a festival weekend. Leave the last day empty to keep going.
- **On certain days of the week:** like weekends only.
- **On a holiday:** pick your country and a holiday, like Thanksgiving or Easter. Prerolls Max looks up the date each year, so holidays that move still land on the right day.
- **On certain dates every year:** like December 24, 25 and 31.
- **On certain days of the month:** like the 1st and the 15th. You can limit it to some months. Days a month doesn't have, like April 31, are skipped.
- **All the time:** every day, until you turn it off.

Turn on **Only at certain times of day** to limit it further, like family intros before 8 pm. If the end time is earlier than the start time, it runs overnight into the next morning.

**3. If schedules overlap.** Sometimes two schedules are on at once, like "Weekends" and "Halloween". Choose what happens:

- **The more important one plays:** rate each schedule from 1 to 10. Holidays usually get a higher number.
- **Mix the intros together:** videos from both can play.
- **Only these intros:** nothing from other schedules or your default intros plays while this one is on. The [never-play list](help:never-play) and [rules](help:rules) still go first: a title on the never-play list gets no intro, and a matching rule (like a Kids rule) plays instead.

The box on the right sums up the schedule in a sentence, so you can check it before saving.

## The calendar

Press **Calendar** above your schedules to see a month at a time. Each day lists the schedules that are on. A line under a day means two or more overlap; the ones that lose are crossed out. Press a day to see which one plays and why.

## Default intros

Default intros play whenever no schedule is on, so there's always something before a movie. At the bottom of [When They Play](app:/schedules), turn on **Play default intros** and pick a collection. As soon as a schedule is on, it takes over.

## Pausing a schedule

Use the switch next to a schedule to turn it off without deleting it.

## Rules come first

On Jellyfin and Emby, [rules](help:rules) are checked before schedules. If a rule matches the title, it picks the intro and the schedules aren't used for that play. On Plex, only schedules and default intros apply.

## Times and time zones

Schedules start and stop on Prerolls Max's own clock. If that clock is in a different time zone from you, Home and this page show a warning. Change it in [Settings](app:/settings#time-zone).

## How exact is it?

- **Jellyfin and Emby:** the Prerolls Max plugin asks before each movie starts, so the right schedule is always used.
- **Plex:** Prerolls Max changes Plex's intro list when a schedule starts or ends. Dates are reliable. A time-of-day change applies to the next movie someone starts, not one that's already playing.

## Playlists

With **Show advanced options** on in Settings, a schedule can play a [playlist](help:playlists) instead of a collection: a set order of intros, like a cinema pre-show. In the first step, choose **A playlist** under **Play from**. Default intros can be a playlist too.
