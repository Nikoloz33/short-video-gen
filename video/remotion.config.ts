// Settings for the Remotion CLI (`npm run studio`). The render worker passes equivalent options itself.
import { Config } from '@remotion/cli/config';

Config.setVideoImageFormat('jpeg');
Config.setJpegQuality(90);
Config.setOverwriteOutput(true);
Config.setCodec('h264');
Config.setCrf(20);
Config.setPixelFormat('yuv420p');
