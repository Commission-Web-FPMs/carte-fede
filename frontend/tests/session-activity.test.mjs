import assert from "node:assert/strict";
import { shouldSignalActivity } from "../src/lib/session-activity.mjs";
for (const type of ["pointerdown","keydown","input","wheel","touchstart"]) assert.equal(shouldSignalActivity({type,isTrusted:true},true,120000,0),true);
for (const type of ["timer","poll","health","scroll","mousemove"]) assert.equal(shouldSignalActivity({type,isTrusted:true},true,120000,0),false);
assert.equal(shouldSignalActivity({type:"pointerdown",isTrusted:false},true,120000,0),false);
assert.equal(shouldSignalActivity({type:"pointerdown",isTrusted:true},false,120000,0),false);
assert.equal(shouldSignalActivity({type:"pointerdown",isTrusted:true},true,59999,0),false);
