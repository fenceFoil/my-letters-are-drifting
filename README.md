# Tornado Time Machine

```plantuml
title Site Components

cloud "Banana.dev\n(Turnkey StableDiffusion)" as banana {

}

cloud "Cloud VM" as cloud {
    [Game Server (app.py)\nPython + FastAPI] as app
}

app -> banana

rectangle Phone as p {
    [Browser] as pb
}

app <-- pb

rectangle "Classroom PC" as pc {
    [Browser] as pcb
}

app <-- pcb
```

```plantuml
title Game Flow
(Prompt Sentence) as prompt
player -> prompt: Add word\nin random spot
"player 2" as p2
prompt <- p2: Add word\nin random spot
prompt -up-> (StableDiffusion): send sentence.
[Classroom PC] as pc
(StableDiffusion)->pc: reply with image.
note top of player: Has goal like "See Paris"

```

## Installation

Get ahold of a Linux cloud VM. My favorite come from Linode, though Amazon AWS offers EC2 as well. This game will use minimal memory and disc space, so 0.5GB to 4GB of ram should work just fine. Images are currently saved to disc every time they're generated, so keep that in mind when choosing disc size if you're running this game for a long time.

Clone this git repo onto your server, maybe in a folder in the home directory. 

Install Python! If you have Debian:
1. `sudo apt install python3`
2. `sudo apt install pip3`
3. `cd` into the src/server folder of this repo
4. `sudo pip3 install -r requirements.txt`

(Note that I should clean up requirements.txt a lot -- there's cruft from other projects in it still).

Set up some required files!
1. Put the URL of your server into `src/server/www/myURL.js`, following the example provided
2. Put the banana keys in `src/server/.env`, which should look like this:

```ini
[DEFAULT]
api_key=2222b2d2-22a2-2222-b222-2e222a222d22
model_key=4444b4d4-44a4-4444-b444-4e444a444d44
```

If you want to have a "bad words" list, put it into `src/server/badWords.txt`. Separate each word with a comma. 

Start the server!

1. From inside The src/server folder, Run `uvicorn app:app --reload --no-access-log --log-level warning --port 80 --host 0.0.0.0`

> This is a hacky way to deploy a FastAPI server! Consider having an access log printed to the console and removing the "reload" flag. Good enough for gamejam though!

![](doc/Screenshot%202022-11-06%20at%2019-01-05%20Driftgame%20Presenter.png)

## Website notes

* Frontend is HTML & JavaScript, with Alpine.js as a framework.

## Tips

If the image from Banana.dev comes back as a blank black square, you've triggered the inexplicably sensitive NSFW filter! One surefire way to get it back normal is to make the next added word "clothed". Another is to remove the added word by clicking it on the presenter dashboard in the pink list to snipe it.

## CREDITS

@fenceFoil -- wrote the game!
@baocin -- pointed out banana.dev and kicked the ideas off!
@dimanor3 Bijan -- wrote the bad word list (omitted from this repo to protect the innocent and my GitHub account)