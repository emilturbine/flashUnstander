#version 440

layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;

layout(std140, binding = 0) uniform Parameters {
    mat4 qt_Matrix;
    float qt_Opacity;
    float extent;
    float spin;
    float tilt;
    float axialTip;
    float selfLit;
    vec3 light;
    float brightness;
    float shadowLight;
    vec3 ringColor;
    vec4 ringPattern;
    float ringSeed;
    float ringPhase;
    float ringReflectivity;
    float terrestrial;
    float weatherDrift;
    float cirrusDrift;
    float weatherEvolution;
    float stormOrigin;
    float weatherReady;
    float detailLevel;
    float materialKind;
    float surfaceReady;
    vec4 storm0;
    vec4 storm1;
    vec4 storm2;
};
layout(binding = 1) uniform sampler2D surface;
layout(binding = 2) uniform sampler2D weather;

vec2 sphereUv(vec2 xy, float z) {
    float localX = xy.x * cos(tilt) + xy.y * sin(tilt);
    float axisY = xy.y * cos(tilt) - xy.x * sin(tilt);
    float localY = axisY * cos(axialTip) + z * sin(axialTip);
    float localZ = z * cos(axialTip) - axisY * sin(axialTip);
    return vec2(atan(localX, localZ) / 6.2831853 + 0.5 - spin / 6.2831853,
                asin(clamp(localY, -1.0, 1.0)) / 3.1415927 + 0.5);
}

vec3 sampleWrapped(sampler2D image, vec2 unwrapped) {
    // Wrap the sample, not its gradients. An atan branch cut must not select
    // a blurrier mip level than adjacent parts of the sphere.
    vec2 du = dFdx(unwrapped);
    vec2 dv = dFdy(unwrapped);
    du.x -= floor(du.x + 0.5);
    dv.x -= floor(dv.x + 0.5);
    const vec2 textureScale = vec2(16.0/17.0, 1.0);
    vec2 uv = vec2(fract(unwrapped.x) + 1.0/32.0, unwrapped.y) * textureScale;
    vec2 filterScale = textureScale * mix(1.0, .88, detailLevel);
    return textureGrad(image, uv, du * filterScale, dv * filterScale).rgb;
}

vec2 weatherFlow(vec2 uv, float rotation, float phase, float altitude) {
    // Rigid drift can keep going forever. Differential motion is a bounded
    // displacement with latitude and never multiplies by elapsed time.
    uv.x -= rotation / 6.2831853;
    float latitude = uv.y - .5;
    float longitudinal = 6.2831853 * uv.x;
    float ebb = sin(phase + 5.4 * latitude);
    uv.x += (.026 + .013*altitude) * cos(5.8*latitude) * ebb;
    uv.y += .012 * cos(3.0*longitudinal - phase + 8.0*latitude)
                 * sin(3.1415927 * clamp(uv.y, 0.0, 1.0));
    return uv;
}

vec2 wrappedOffset(vec2 uv, vec2 center) {
    return vec2(fract(uv.x - center.x + .5) - .5, uv.y - center.y);
}

vec2 frontFlow(vec2 uv, float phase) {
    vec2 flow = weatherFlow(uv, weatherDrift, phase, 0.0);
    float latitude = flow.y - .5;
    float beltDistance = (abs(latitude) - .27) * 9.0;
    float belt = exp(-beltDistance*beltDistance);
    float longitude = 6.2831853*flow.x;
    // Follow the migrating midlatitude front as a coherent curve.
    flow.y += .032*belt*sin(2.0*longitude - phase + 3.0*latitude);
    flow.x += .024*belt*cos(longitude + phase);
    return flow;
}

float regionalEvolution(vec2 uv, float phase) {
    float longitude = 6.2831853*uv.x;
    float region = 1.22*sin(longitude + 4.3*uv.y)
                 + .71*cos(2.0*longitude - 8.0*uv.y)
                 + .34*sin(3.0*longitude + 6.2831853*uv.y);
    return smoothstep(.16, .84, .5 - .5*cos(phase + region));
}

float atlasStormWeight(vec2 uv, vec2 center) {
    vec2 distance = wrappedOffset(uv, center) / vec2(.102, .133);
    return 1.0 - smoothstep(.42, 1.18, length(distance));
}

float frontDensity(vec2 uv, vec2 centerA, vec2 centerB, vec2 centerC) {
    float originalStorm = max(atlasStormWeight(uv, centerA),
                              max(atlasStormWeight(uv, centerB), atlasStormWeight(uv, centerC)));
    // Soften the atlas's stationary cyclones beneath the independently moving ones.
    return sampleWrapped(weather, uv).g * (1.0 - .76*originalStorm);
}

float movingStorm(vec2 uv, vec2 origin, vec4 state, float direction, float turbulence) {
    vec2 relative = wrappedOffset(uv, origin + state.xy) / vec2(.102, .133);
    float radius = length(relative);
    float heading = atan(relative.y, relative.x + .0000001);
    float spiral = 2.0*heading + direction*(7.1*radius + 2.4*log(radius+.09) - state.z);
    float arm = .5 + .5*cos(spiral + 1.3*(turbulence-.4));
    float relief = smoothstep(.06, .28, radius) * (1.0-smoothstep(.36, 1.12, radius));
    float broken = .56 + .44*smoothstep(.06, .67, turbulence);
    return .91 * state.w * relief * broken * smoothstep(.28, .88, arm);
}

float lowerWeather(vec2 shellUv) {
    vec2 centerA = vec2(.13 + stormOrigin, .66);
    vec2 centerB = vec2(.48 + stormOrigin, .30);
    vec2 centerC = vec2(.80 + stormOrigin, .72);
    vec2 flow = frontFlow(shellUv, weatherEvolution);
    vec2 alternate = frontFlow(shellUv + vec2(.28, .018), weatherEvolution + 1.7);
    float blend = regionalEvolution(flow, weatherEvolution);
    float a = frontDensity(flow, centerA, centerB, centerC);
    float b = frontDensity(alternate, centerA, centerB, centerC);
    float front = mix(a, b, blend);
    float storms = max(movingStorm(flow, centerA, storm0, 1.0, front),
                       max(movingStorm(flow, centerB, storm1, -1.0, front),
                           movingStorm(flow, centerC, storm2, 1.0, front)));
    return front + (1.0 - front)*storms;
}

float sphereCoverage(vec2 xy, float radial) {
    vec2 dx = dFdx(xy);
    vec2 dy = dFdy(xy);
    float pixel = max(.0001, max(length(dx), length(dy)));
    if (abs(radial - 1.0) > pixel)
        return step(radial, 1.0);

    // Integrate coverage at four subpixel positions along the silhouette.
    // Texture and lighting still use the actual fragment center.
    vec2 cornerA = .28 * (dx + dy);
    vec2 cornerB = .28 * (dx - dy);
    float edge = .33 * pixel;
    vec4 distances = vec4(length(xy+cornerA), length(xy-cornerA),
                          length(xy+cornerB), length(xy-cornerB));
    return 1.0 - dot(smoothstep(1.0-edge, 1.0+edge, distances), vec4(.25));
}

vec3 raisedTerrainNormal(vec3 sphereNormal, float elevation) {
    // Recover the height gradient on the actual sphere tangent plane.
    // Increasing elevation displaces the surface outward along sphereNormal.
    vec3 dx = dFdx(sphereNormal);
    vec3 dy = dFdy(sphereNormal);
    vec3 xDual = cross(dy, sphereNormal);
    vec3 yDual = cross(sphereNormal, dx);
    float determinant = dot(dx, xDual);
    vec3 surfaceGradient = (xDual*dFdx(elevation) + yDual*dFdy(elevation))
                         * sign(determinant) / max(abs(determinant), .00000001);
    float strength = .037 * smoothstep(.06, .24, sphereNormal.z);
    return normalize(sphereNormal - strength * surfaceGradient);
}

vec3 ovalVortex(vec3 atmosphere, vec2 uv, vec2 center, vec2 size,
                 float phase, float strength, vec3 pigment, vec3 vapor) {
    vec2 delta = wrappedOffset(uv, center) / size;
    float radius = length(delta);
    float mask = 1.0 - smoothstep(.70, 1.06, radius);
    float heading = atan(delta.y, delta.x + .0000001);
    float spiral = 2.0*heading + 8.0*radius + 2.0*log(radius+.18) - phase;
    float ridge = .5 + .5*cos(spiral);
    // The core remains coherent while the spiral's clouds circulate around it.
    float wall = smoothstep(.16, .42, radius) * (.20 + .65*ridge);
    float rim = smoothstep(.66, .84, radius) * (1.0-smoothstep(.86, 1.04, radius));
    vec3 stormColor = mix(pigment, vapor, clamp(wall + .24*rim, 0.0, 1.0));
    return mix(atmosphere, stormColor, mask * strength);
}

vec3 giantAtmosphere(vec2 uv, bool icy) {
    float longitude = 6.2831853 * uv.x;
    float wave = sin(3.0*longitude + weatherEvolution) + .46*sin(7.0*longitude - weatherEvolution);
    float latitude = uv.y + (icy ? .005 : .011)*wave;
    float profile = sin((icy ? 28.0 : 44.0) * latitude + .28*sin(19.0*latitude));
    float beltEdge = max(.12, .6*fwidth(profile));
    float belt = smoothstep(-.32-beltEdge, .34+beltEdge, profile);
    // Two full textures are sampled in opposite directions. Belt weights are
    // spatial, so long runtimes cannot keep shearing one pattern into stripes.
    vec2 east = weatherFlow(vec2(uv.x, latitude), weatherDrift + stormOrigin, weatherEvolution, 0.0);
    vec2 west = weatherFlow(vec2(uv.x, latitude), -cirrusDrift + stormOrigin, -weatherEvolution, .7);
    float boundary = 4.0*belt*(1.0-belt);
    float eddy = sin(8.0*longitude + 33.0*latitude - 2.0*weatherEvolution);
    east.y += boundary*(icy ? .002 : .006)*eddy;
    west.y -= boundary*(icy ? .002 : .005)*eddy;
    vec3 eastCloud = sampleWrapped(surface, east);
    vec3 westCloud = sampleWrapped(surface, west);
    vec3 mixCloud = mix(eastCloud, westCloud, belt);

    if (icy) {
        vec3 dark = vec3(.19, .40, .63);
        vec3 lightBelt = vec3(.50, .71, .84);
        vec3 color = mix(mix(dark, lightBelt, .24 + .52*belt), mixCloud, .64);
        float vapor = sampleWrapped(surface, west + vec2(.18, .012)).b;
        float highCloud = smoothstep(.67, .84, vapor) * (.14+.16*boundary);
        color = mix(color, vec3(.75, .86, .96), highCloud);
        float phase = weatherEvolution + 2.4*stormOrigin;
        vec2 center = vec2(.57 + stormOrigin + .083*sin(phase), .64+.024*cos(phase));
        float presence = .55 + .30*sin(phase + 1.1);
        return ovalVortex(color, uv, center, vec2(.057, .064), phase, presence,
                          vec3(.15, .31, .54), vec3(.59, .74, .88));
    }

    float longitudeDetail = 31.0*longitude + 64.0*latitude;
    float visibleDetail = 1.0 - smoothstep(.45, 2.15, fwidth(longitudeDetail));
    float curls = sin(longitudeDetail + 2.0*eddy - 3.0*weatherEvolution) * visibleDetail;
    vec3 darkBelt = vec3(.47, .29, .17);
    vec3 creamZone = vec3(.89, .77, .58);
    vec3 atmosphere = mix(mix(creamZone, darkBelt, .12 + .78*belt), mixCloud, .59);
    atmosphere += vec3(.061, .053, .042) * curls * boundary;

    float phase = weatherEvolution + 2.1*stormOrigin;
    vec2 largeCenter = vec2(.57 + stormOrigin + .074*sin(phase), .66 + .017*sin(phase+1.0));
    atmosphere = ovalVortex(atmosphere, uv, largeCenter, vec2(.092, .078),
                           phase*2.0, .85, vec3(.64, .29, .17), vec3(.93, .65, .42));
    vec2 smallCenter = vec2(.26 + stormOrigin - .09*cos(phase), .33 + .025*sin(phase));
    float smallPresence = .66*smoothstep(-.42, .68, sin(phase + 1.7));
    return ovalVortex(atmosphere, uv, smallCenter, vec2(.037, .042), -phase*3.0,
                     smallPresence, vec3(.57, .41, .30), vec3(.94, .83, .65));
}

vec2 impactRelief(vec2 uv, vec2 center, vec2 size) {
    vec2 relative = wrappedOffset(uv, center) / size;
    float radius = length(relative);
    float bowl = -(1.0 - smoothstep(.14, .88, radius)) * .22;
    float rimDistance = (radius - .88) / .135;
    float rim = .12*exp(-rimDistance*rimDistance);
    float rays = (1.0-smoothstep(.88, 1.54, radius)) * smoothstep(.72, 1.08, radius);
    float heading = atan(relative.y, relative.x + .0000001);
    rays *= .55 + .45*sin(11.0*heading + 3.0*radius);
    return vec2(bowl + rim, rays);
}

vec2 rockyImpacts(vec2 uv) {
    vec2 relief = impactRelief(uv, vec2(.21 + stormOrigin, .36), vec2(.041, .055));
    relief += impactRelief(uv, vec2(.56 + stormOrigin, .57), vec2(.063, .082));
    relief += impactRelief(uv, vec2(.72 + stormOrigin, .39), vec2(.025, .035));
    relief += impactRelief(uv, vec2(.91 + stormOrigin, .67), vec2(.034, .045));
    relief += impactRelief(uv, vec2(.39 + stormOrigin, .64), vec2(.023, .029));
    return relief;
}

float ringHash(float index) {
    return fract(sin(index * 19.489 + ringSeed * .28791) * 43758.5468);
}

float ringDensity(float radius, float pixel) {
    float width = ringPattern.y - ringPattern.x;
    float x = (radius - ringPattern.x) / width;
    float edge = clamp(.55 * pixel / width, .002, .12);
    float envelope = smoothstep(-edge, edge, x) * (1.0 - smoothstep(1.0-edge, 1.0+edge, x));
    float bands = ringPattern.z;
    float density = .065;
    for (int i = 0; i < 8; ++i) {
        if (float(i) >= bands)
            break;
        float index = float(i);
        float center = (index + .5 + .49*(ringHash(index+10.0)-.5)) / bands;
        float halfWidth = mix(.20, .63, ringHash(index+23.0)) / bands;
        float distance = abs(x - center);
        float band = 1.0 - smoothstep(max(0.0,halfWidth-edge), halfWidth+edge, distance);
        density += mix(.25, .66, ringHash(index+46.0)) * band;
    }

    for (int i = 0; i < 3; ++i) {
        if (float(i) >= ringPattern.w)
            break;
        float index = float(i);
        float center = (index + 1.0 + .34*(ringHash(index+70.0)-.5)) / (ringPattern.w+1.0);
        float halfWidth = mix(.011, .040, ringHash(index+94.0));
        float gap = 1.0 - smoothstep(max(0.0,halfWidth-edge), halfWidth+edge, abs(x-center));
        density *= 1.0 - .97*gap;
    }

    // Filter the narrow dusty striations when they are smaller than a pixel.
    float detail = 1.0 - smoothstep(.24, .80, pixel*49.0);
    float texture = .92 + detail*(.07*cos(111.0*x + ringSeed) + .08*sin(204.0*x + .1*ringSeed));
    return clamp(density * texture * envelope, 0.0, .87);
}

float ringParticles(vec3 point, vec3 plane, float radius) {
    vec3 tangent = normalize(cross(plane, vec3(0.0, 0.0, 1.0)));
    vec3 bitangent = cross(plane, tangent);
    float azimuth = (atan(dot(point,bitangent), dot(point,tangent)+.0000001) - ringPhase)
                  / 6.2831853;
    float radial = (radius-ringPattern.x)/(ringPattern.y-ringPattern.x);
    vec2 cells = vec2(fract(azimuth)*96.0, radial*8.0);
    vec2 cell = floor(cells);
    float key = cell.x + 97.0*cell.y;
    float exists = step(.983 - .034*ringReflectivity, ringHash(key + 200.0));
    vec2 center = vec2(ringHash(key+440.0), ringHash(key+710.0)) * .50 + .25;
    float size = mix(.055, .13, ringHash(key + 110.0));

    // The phase wraps around the ring. Unwrap its derivatives independently
    // so a particle keeps the same antialiasing across the angular seam.
    float du = dFdx(azimuth);
    float dv = dFdy(azimuth);
    du -= floor(du+.5);
    dv -= floor(dv+.5);
    float footprint = max(96.0*(abs(du)+abs(dv)), fwidth(radial)*8.0);
    float aa = clamp(footprint*.36, .017, .18);
    float shape = 1.0 - smoothstep(max(.0,size-aa), size+aa, length(fract(cells)-center));
    float resolved = 1.0 - smoothstep(.25, .85, footprint);
    vec3 facet = normalize(plane + tangent*(ringHash(key+77.0)-.5)
                                + bitangent*(ringHash(key+87.0)-.5));
    vec3 halfway = light + vec3(0.0, 0.0, 1.0);
    halfway /= max(length(halfway), .001);
    float specular = pow(abs(dot(facet,halfway)), 7.0);
    return exists * shape * resolved * ringReflectivity * (.29 + .71*specular);
}

vec3 untexturedSurface(vec2 uv) {
    if (materialKind < .5) {
        float heat = .5 + .5*sin(126.0*uv.y + 3.0*sin(52.0*uv.x))
                            * cos(82.0*uv.x - 17.0*uv.y);
        return mix(vec3(1.0, .56, .16), vec3(1.0, .80, .34), heat);
    }
    if (materialKind < 1.5)
        return vec3(.12, .31, .48);
    if (materialKind < 2.5)
        return vec3(.65, .40, .29);
    if (materialKind < 3.5)
        return vec3(.76, .61, .42);
    return vec3(.42, .64, .77);
}

void main() {
    vec2 xy = (qt_TexCoord0 * 2.0 - 1.0) * extent;
    float radial = length(xy);
    float z = sqrt(max(0.0, 1.0 - dot(xy, xy)));
    float alpha = sphereCoverage(xy, radial);
    vec3 normal = vec3(xy, z);
    vec2 uv = sphereUv(xy, z);
    vec3 color = untexturedSurface(uv);
    if (surfaceReady > 0.0) {
        vec3 material = materialKind > 2.5 ? giantAtmosphere(uv, materialKind > 3.5)
                                          : sampleWrapped(surface, uv);
        color = mix(color, material, surfaceReady);
    }
    if (selfLit > 0.5) {
        color *= 0.745 + 0.28 * pow(z, 0.57);

        // Composite the corona and globe in one premultiplied pass. The corona
        // stays continuous under the anti-aliased edge of the photosphere.
        float haloRadius = radial / extent;
        vec4 inner = vec4(255.0, 182.0, 83.0, 140.0) / 255.0;
        vec4 rim = vec4(255.0, 149.0, 62.0, 75.0) / 255.0;
        vec4 outer = vec4(233.0, 111.0, 44.0, 26.0) / 255.0;
        vec4 corona;
        if (haloRadius < 0.46)
            corona = mix(inner, rim, clamp((haloRadius-0.40)/0.06, 0.0, 1.0));
        else if (haloRadius < 0.64)
            corona = mix(rim, outer, (haloRadius-0.46)/0.18);
        else
            corona = vec4(outer.rgb, outer.a*(1.0-smoothstep(0.64, 1.0, haloRadius)));
        float glowAlpha = clamp(corona.a * brightness, 0.0, 1.0) * (1.0-alpha);
        fragColor = vec4(clamp(color*brightness, 0.0, 1.0)*alpha
                       + corona.rgb*glowAlpha, alpha+glowAlpha) * qt_Opacity;
        return;
    } else {
        float incidence = dot(normal, light);
        // Keep the penumbra about 3.5 screen pixels wide even during close-ups.
        float feather = max(.0006, 1.75 * fwidth(incidence));
        float daylight = smoothstep(-feather, feather, incidence);
        float diffuse = daylight * mix(.33, 1.0, pow(max(0.0, incidence), .72));
        if (materialKind > 1.5 && materialKind < 2.5 && detailLevel > 0.0) {
            vec2 impacts = rockyImpacts(uv);
            float mineral = dot(color, vec3(.34, .52, .14));
            float elevation = (.33*mineral + impacts.x) * detailLevel;
            vec3 rockNormal = raisedTerrainNormal(normal, elevation);
            float relief = clamp((dot(rockNormal, light) - incidence)*1.9, -.32, .30);
            color *= 1.0 + relief * daylight;
            color += vec3(.17, .127, .090) * impacts.y * detailLevel * daylight;
        }
        color *= mix(shadowLight, 1.055, diffuse);
        float litRim = mix(0.12, 1.0, smoothstep(-0.3, 0.2, incidence));
        if (terrestrial > 0.5) {
            if (weatherReady > 0.0) {
                vec2 shell = xy / 1.018;
                float shellZ = sqrt(max(0.0, 1.0 - dot(shell, shell)));
                vec2 shellUv = sphereUv(shell, shellZ);
                float cloud = lowerWeather(shellUv);
                vec2 highCloudUv = weatherFlow(shellUv + vec2(0.0, .012), cirrusDrift,
                                               weatherEvolution + .8, 1.0);
                float highEvolution = regionalEvolution(highCloudUv, weatherEvolution + 1.4);
                float cirrus = mix(sampleWrapped(weather, highCloudUv).b,
                                   sampleWrapped(weather, highCloudUv + vec2(.23, -.024)).b,
                                   .12 + .7*highEvolution);
                float elevation = sampleWrapped(weather, uv).r;
                float ocean = 1.0 - smoothstep(.462, .515, elevation);
                float dryLand = smoothstep(.53, .62, elevation);
                vec3 reliefNormal = raisedTerrainNormal(normal, elevation);
                float reliefLight = clamp((dot(reliefNormal, light) - incidence)*1.65, -.28, .25);
                color *= 1.0 + reliefLight*dryLand*daylight*weatherReady;
                vec2 shadowOffset = vec2(-light.x, light.y)*.012;
                float shadow = lowerWeather(shellUv + shadowOffset);
                float cloudShadow = smoothstep(.27, .67, shadow);
                color *= 1.0 - .27 * cloudShadow * daylight * weatherReady;

                // Keep blue water in the diffuse pass; add directional glint
                // and grazing reflection rather than a broad white hotspot.
                float waveX = 6.2831853*(57.0*uv.x + 13.0*uv.y) + weatherDrift*2.0;
                float waveY = 6.2831853*(31.0*uv.x - 29.0*uv.y) - weatherDrift*3.0;
                float waveDetail = 1.0 - smoothstep(.42, 1.9, max(fwidth(waveX), fwidth(waveY)));
                vec3 waterNormal = normalize(normal + vec3(sin(waveX), cos(waveY), 0.0)
                                                      * (.021 * waveDetail));
                vec3 halfVector = light + vec3(0.0, 0.0, 1.0);
                halfVector /= max(length(halfVector), .001);
                float angle = max(0.0, dot(waterNormal, halfVector));
                float broadGlint = .09 * pow(angle, 18.0);
                float sharpGlint = .34 * pow(angle, 91.0);
                float fresnel = .024 + .18 * pow(1.0-z, 5.0);
                float clearWater = ocean * daylight * (1.0-.86*cloud) * weatherReady;
                color += (vec3(0.88, 0.81, 0.66) * (broadGlint + sharpGlint)
                          + vec3(0.20, 0.38, 0.57) * fresnel) * clearWater;

                float cloudAA = min(.055, .48 * fwidth(cloud));
                float cloudBody = smoothstep(.07-cloudAA, .87+cloudAA, cloud);
                float cover = (1.0 - (1.0-.75*cloudBody) * (1.0-.28*cirrus)) * weatherReady;
                float cloudIncidence = dot(vec3(shell, shellZ), light);
                float cloudFeather = max(.001, 1.75 * fwidth(cloudIncidence));
                float cloudDay = smoothstep(-cloudFeather, cloudFeather, cloudIncidence);
                float cloudLight = mix(.23, .51 + .49*pow(max(0.0, cloudIncidence), .48), cloudDay);
                float raisedEdge = clamp(cloud - shadow, -.27, .25);
                vec3 cloudColor = vec3(0.83, 0.90, 0.96)
                               * (cloudLight + .45*raisedEdge*cloudDay);
                color = mix(color, cloudColor, cover);
            }
            vec3 air = vec3(0.22, 0.56, 0.93);
            color += air * pow(1.0-z, 3.1) * litRim * .51;
            float outerAir = exp(-max(0.0, radial-1.0)*78.0)
                           * (1.0-smoothstep(1.018, 1.05, radial));
            float airAlpha = .25 * outerAir * litRim * (1.0-alpha);
            color = (color*alpha + air*airAlpha) / max(alpha + airAlpha, .0001);
            alpha += airAlpha;
        } else {
            vec3 haze = materialKind > 3.5 ? vec3(.21, .49, .79) :
                        materialKind > 2.5 ? vec3(.49, .33, .20) : vec3(.25, .18, .12);
            color += haze * pow(1.0 - z, 3.3) * litRim;
        }

        if (ringPattern.y > ringPattern.x && ringPattern.z > 0.0) {
            vec3 plane = vec3(-0.26, -0.91, 0.322);
            float ringZ = -dot(plane.xy, xy) / plane.z;
            vec3 ring = vec3(xy, ringZ);
            float r = length(ring);
            float density = ringDensity(r, max(fwidth(r), .004));
            float along = -dot(ring, light);
            float clearance = 1.0 - r*r + along*along;
            float shadowEdge = max(.002, .55*fwidth(clearance));
            float shadow = step(0.0, along) * smoothstep(-shadowEdge, shadowEdge, clearance);
            float slope = dot(plane, light);
            if (abs(slope) > 0.006) {
                float travel = -dot(plane, normal) / slope;
                float crossing = length(normal + travel * light);
                float projectedDust = ringDensity(crossing, max(.005, fwidth(crossing)));
                color *= 1.0 - .58 * projectedDust * step(0.0, travel);
            }
            float glint = ringParticles(ring, plane, r) * (1.0-shadow)
                        * smoothstep(.075, .30, density);
            density = clamp(density + .75*glint, 0.0, .96);
            vec3 dust = ringColor * (0.54 + 0.40*abs(dot(plane,light))) * (1.0-0.72*shadow);
            dust = mix(dust, vec3(1.0, .95, .86), glint);
            bool inFront = ringZ > z;
            float visible = density * (inFront ? 1.0 : 1.0-alpha);
            float globe = alpha * (inFront ? 1.0-density : 1.0);
            fragColor = vec4(clamp(color*brightness, 0.0, 1.0)*globe
                           + clamp(dust*brightness, 0.0, 1.0)*visible,
                             globe+visible) * qt_Opacity;
            return;
        }
    }
    fragColor = vec4(clamp(color*brightness, 0.0, 1.0)*alpha, alpha) * qt_Opacity;
}
